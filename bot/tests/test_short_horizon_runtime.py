from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from aegis.intel.short_horizon_runtime import (
    ShortHorizonPredictor,
    resample_runtime_quotes,
    seed_quote_buffer,
)


def test_short_horizon_runtime_is_fail_closed_without_artifact(tmp_path: Path):
    predictor = ShortHorizonPredictor(tmp_path / "missing")

    result = predictor.predict(symbol="EURUSD", quote_buffer=None, now_ts=1.0)
    assert result["abstain"] is True
    assert result["prediction_reason"] == "artifact_not_found"
    assert predictor.snapshot()["status"] == "missing_artifact"
    assert predictor.snapshot()["reason"] == "artifact_not_found"


def test_short_horizon_runtime_rejects_non_short_horizon_metadata(tmp_path: Path):
    path = tmp_path / "model"
    path.mkdir()
    (path / "metadata.json").write_text('{"schema":"ml_pipeline.v1"}', encoding="utf-8")

    predictor = ShortHorizonPredictor(path)

    result = predictor.predict(symbol="EURUSD", quote_buffer=None, now_ts=1.0)
    assert result["abstain"] is True
    assert result["prediction_reason"] == "schema_mismatch"
    assert predictor.snapshot()["status"] == "invalid_artifact"
    assert predictor.snapshot()["reason"] == "schema_mismatch"


def test_seed_quote_buffer_uses_only_valid_broker_quotes():
    class Buffer:
        def __init__(self):
            self.rows = []

        def record(self, symbol, timestamp, bid, ask):
            self.rows.append((symbol, timestamp, bid, ask))

    buffer = Buffer()
    count = seed_quote_buffer(
        buffer,
        "EURUSD",
        [
            {"time": 1, "bid": 1.1, "ask": 1.1001},
            {"time": 2, "bid": 0, "ask": 1.2},
        ],
    )

    assert count == 1
    assert len(buffer.rows) == 1


def test_runtime_quotes_use_the_training_one_second_cadence():
    frame = pd.DataFrame(
        {
            "time": pd.to_datetime(
                [
                    "2026-08-25T10:00:00.100Z",
                    "2026-08-25T10:00:00.900Z",
                    "2026-08-25T10:00:01.200Z",
                ],
                utc=True,
            ),
            "bid": [1.1000, 1.1001, 1.1002],
            "ask": [1.1002, 1.1003, 1.1004],
        }
    )

    result = resample_runtime_quotes(frame)

    assert len(result) == 2
    assert result.iloc[0]["bid"] == 1.1001
    assert result.iloc[1]["bid"] == 1.1002


def test_captured_exit_artifact_uses_captured_oos_expectancy_for_runtime_ev(tmp_path: Path):
    class Pipeline:
        models = [object(), object()]

        def get_calibrated_ensemble_prediction(self, row, **kwargs):
            return {
                "probability": [0.8],
                "decision": [True],
                "abstain": [False],
                "model_agreement": [1.0],
                "uncertainty": [0.01],
            }

    class Buffer:
        points = [
            SimpleNamespace(timestamp=1787659200.0, bid=1.1, ask=1.1002),
            SimpleNamespace(timestamp=1787659201.0, bid=1.1001, ask=1.1003),
        ]

    predictor = ShortHorizonPredictor(tmp_path / "missing")
    predictor.pipeline = Pipeline()
    predictor.status = "ready"
    predictor.execution_status = "EXECUTION_CANDIDATE"
    predictor.metadata = {
        "horizons_s": [10],
        "decision_horizon_s": 10,
        "target_definition": "captured_exit_replay",
        "threshold": 0.5,
        "min_model_agreement": 0.6,
        "max_uncertainty": 0.2,
        "authorized_symbols": ["EURUSD"],
        "threshold_by_symbol_horizon": {"EURUSD": {"10": 0.7}},
        "oos": {
            "sealed_by_horizon": {
                "10": {
                    "mean_captured_exit_return": 0.001,
                    "captured_exit_lcb95_return": 0.0005,
                }
            },
            "sealed_by_symbol_horizon": {
                "EURUSD": {
                    "10": {
                        "mean_captured_exit_return": 0.002,
                        "captured_exit_lcb95_return": 0.001,
                    }
                }
            },
        },
    }
    quote_buffer = SimpleNamespace(buffers={"EURUSD": Buffer()})

    result = predictor.predict(
        symbol="EURUSD",
        quote_buffer=quote_buffer,
        now_ts=1787659201.0,
        side="buy",
        notional_usd=100.0,
    )

    assert result is not None
    assert result["harvest_mode"] == "captured_exit_replay"
    assert result["expected_harvest_return"] is None
    assert result["expected_captured_exit_return"] == 0.002
    assert result["expected_net_pnl"] > 0.0
    assert result["expected_net_pnl_lcb95"] > 0.0
    assert result["threshold"] == 0.7
    assert result["by_horizon"]["10"]["threshold"] == 0.7


def test_execution_candidate_rejects_symbol_without_exact_scope_permission(tmp_path: Path):
    predictor = ShortHorizonPredictor(tmp_path / "missing")
    predictor.execution_status = "EXECUTION_CANDIDATE"
    predictor.status = "ready"
    predictor.metadata = {
        "target_definition": "captured_exit_replay",
        "authorized_symbols": ["GBPUSD"],
    }

    result = predictor.predict(symbol="EURUSD", quote_buffer=None, now_ts=1.0)

    assert result is not None
    assert result["abstain"] is True
    assert result["prediction_reason"] == "symbol_not_authorized"


def test_runtime_exposes_precise_abstention_diagnostics(tmp_path: Path):
    class Pipeline:
        models = [object(), object()]

        def get_calibrated_ensemble_prediction(self, row, **kwargs):
            return {
                "probability": [0.8],
                "decision": [False],
                "abstain": [True],
                "model_agreement": [0.5],
                "uncertainty": [0.8],
            }

    class Buffer:
        points = [
            SimpleNamespace(timestamp=1787659200.0, bid=1.1, ask=1.1002),
            SimpleNamespace(timestamp=1787659201.0, bid=1.1001, ask=1.1003),
        ]

    predictor = ShortHorizonPredictor(tmp_path / "missing")
    predictor.pipeline = Pipeline()
    predictor.status = "shadow_only"
    predictor.metadata = {
        "horizons_s": [10],
        "decision_horizon_s": 10,
        "threshold": 0.5,
        "min_model_agreement": 0.6,
        "max_uncertainty": 0.2,
    }
    result = predictor.predict(
        symbol="EURUSD",
        quote_buffer=SimpleNamespace(buffers={"EURUSD": Buffer()}),
        now_ts=1787659201.0,
    )

    assert result is not None
    assert result["abstain_reason"] == "artifact_shadow_only"
    assert result["abstain"] is True


def test_runtime_diagnostics_handle_vector_model_outputs(tmp_path: Path):
    class Pipeline:
        models = [object(), object()]

        def get_calibrated_ensemble_prediction(self, row, **kwargs):
            return {
                "probability": [0.8],
                "decision": [False],
                "abstain": [True],
                "model_agreement": [2.0 / 3.0],
                "uncertainty": [0.8],
            }

    class Buffer:
        points = [
            SimpleNamespace(timestamp=1787659200.0, bid=1.1, ask=1.1002),
            SimpleNamespace(timestamp=1787659201.0, bid=1.1001, ask=1.1003),
        ]

    predictor = ShortHorizonPredictor(tmp_path / "missing")
    predictor.pipeline = Pipeline()
    predictor.status = "shadow_only"
    predictor.metadata = {
        "horizons_s": [10],
        "decision_horizon_s": 10,
        "min_model_agreement": 0.6,
        "max_uncertainty": 0.2,
    }
    result = predictor.predict(
        symbol="EURUSD",
        quote_buffer=SimpleNamespace(buffers={"EURUSD": Buffer()}),
        now_ts=1787659201.0,
    )

    assert result is not None
    assert result["abstain_reason"] == "artifact_shadow_only"
    assert result["abstain"] is True
