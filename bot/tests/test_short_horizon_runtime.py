from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from aegis.intel.short_horizon_runtime import (
    ShortHorizonPredictor,
    execution_candidate_has_current_promotion_policy,
    resample_runtime_quotes,
    seed_quote_buffer,
)
from aegis.intel.quote_buffer import QuoteBuffer


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


def test_execution_candidate_loader_rejects_empty_authorized_symbols(tmp_path: Path):
    path = tmp_path / "model"
    path.mkdir()
    (path / "metadata.json").write_text(
        """{
          \"schema\": \"short_horizon_ensemble.v1\",
          \"execution_status\": \"EXECUTION_CANDIDATE\",
          \"target_definition\": \"captured_exit_replay\",
          \"dataset_hash\": \"dataset\",
          \"validation_hash\": \"validation\",
          \"horizons_s\": [10],
          \"decision_horizon_s\": 10,
          \"authorized_symbols\": [],
          \"oos\": {\"sealed_by_symbol_horizon\": {}},
          \"promotion_policy\": {
            \"min_captured_exit_losses\": 10,
            \"requires_positive_test_and_sealed_lcb95\": true
          }
        }""",
        encoding="utf-8",
    )

    predictor = ShortHorizonPredictor(path)

    assert predictor.snapshot()["status"] == "invalid_artifact"
    assert predictor.snapshot()["reason"] == "execution_requires_authorized_symbols"
    assert predictor.pipeline is None


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


def test_quote_buffer_exports_only_observed_quotes_for_counterfactual_replay():
    buffer = QuoteBuffer()
    buffer.record("EURUSD", 10.0, 1.1000, 1.1002)
    buffer.record("EURUSD", 11.0, 1.1001, 1.1003)
    buffer.record("EURUSD", 12.0, 1.1002, 1.1004)

    assert buffer.quotes_between("EURUSD", 10.5, 11.5) == [
        {"timestamp": 11.0, "bid": 1.1001, "ask": 1.1003}
    ]


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


def test_runtime_learns_distinct_net_ev_for_each_horizon(tmp_path: Path):
    class Pipeline:
        models = [object(), object()]

        def get_calibrated_ensemble_prediction(self, row, **kwargs):
            horizon = int(float(row["horizon_s"].iloc[0]))
            return {
                "probability": [0.60 if horizon == 3 else 0.80],
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
    predictor.execution_status = "SHADOW_ONLY_NO_POSITIVE_OOS"
    predictor.metadata = {
        "horizons_s": [3, 20],
        "decision_horizon_s": 3,
        "target_definition": "captured_exit_replay",
        "threshold": 0.5,
        "min_model_agreement": 0.6,
        "max_uncertainty": 0.2,
        "oos": {
            "sealed_by_horizon": {
                "3": {
                    "mean_captured_exit_return": 0.0001,
                    "captured_exit_lcb95_return": 0.00005,
                },
                "20": {
                    "mean_captured_exit_return": 0.0003,
                    "captured_exit_lcb95_return": 0.0002,
                },
            }
        },
    }

    result = predictor.predict(
        symbol="EURUSD",
        quote_buffer=SimpleNamespace(buffers={"EURUSD": Buffer()}),
        now_ts=1787659201.0,
        side="buy",
        broker_spec={
            "trade_tick_value": 1.0,
            "trade_tick_size": 0.0001,
            "volume_min": 0.01,
        },
        quantity=0.01,
    )

    assert result["by_horizon"]["3"]["probability"] != result["by_horizon"]["20"]["probability"]
    assert result["by_horizon"]["3"]["expected_net_pnl"] != result["by_horizon"]["20"]["expected_net_pnl"]
    assert result["decision_horizon_s"] == 20


def test_runtime_exit_prediction_can_be_locked_to_ticket_horizon(tmp_path: Path):
    class Pipeline:
        models = [object(), object()]

        def get_calibrated_ensemble_prediction(self, row, **kwargs):
            horizon = int(float(row["horizon_s"].iloc[0]))
            return {
                "probability": [0.8 if horizon == 3 else 0.6],
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
    predictor.execution_status = "SHADOW_ONLY_NO_POSITIVE_OOS"
    predictor.metadata = {
        "horizons_s": [3, 20],
        "decision_horizon_s": 3,
        "target_definition": "captured_exit_replay",
        "threshold": 0.5,
        "min_model_agreement": 0.6,
        "max_uncertainty": 0.2,
        "oos": {"sealed_by_horizon": {
            "3": {"mean_captured_exit_return": 0.0001, "captured_exit_lcb95_return": 0.00005},
            "20": {"mean_captured_exit_return": 0.0003, "captured_exit_lcb95_return": 0.0002},
        }},
    }

    result = predictor.predict(
        symbol="EURUSD",
        quote_buffer=SimpleNamespace(buffers={"EURUSD": Buffer()}),
        now_ts=1787659201.0,
        side="buy",
        horizon_s=3,
        notional_usd=100.0,
    )

    assert set(result["by_horizon"]) == {"3"}
    assert result["decision_horizon_s"] == 3


def test_runtime_compares_buy_and_sell_and_selects_best_positive_side(tmp_path: Path):
    class Pipeline:
        models = [object(), object()]

        def get_calibrated_ensemble_prediction(self, row, **kwargs):
            is_buy = bool(float(row["side_buy"].iloc[0]))
            return {
                "probability": [0.62 if is_buy else 0.84],
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
        "oos": {
            "sealed_by_symbol_horizon": {
                "EURUSD": {
                    "10": {
                        "mean_captured_exit_return": 0.001,
                        "captured_exit_lcb95_return": 0.0005,
                    }
                }
            }
        },
    }

    result = predictor.predict_sides(
        symbol="EURUSD",
        quote_buffer=SimpleNamespace(buffers={"EURUSD": Buffer()}),
        now_ts=1787659201.0,
        broker_spec={
            "trade_tick_value": 1.0,
            "trade_tick_size": 0.0001,
            "volume_min": 0.01,
        },
        quantity=0.01,
    )

    assert result["selected_side"] == "sell"
    assert result["side_comparison"]["ranking"] == ["sell", "buy"]
    assert set(result["side_predictions"]) == {"buy", "sell"}
    assert result["side_predictions"]["buy"]["feature_snapshot"] == result["side_predictions"]["sell"]["feature_snapshot"]


def test_runtime_side_comparison_abstains_when_both_sides_are_unavailable(tmp_path: Path):
    predictor = ShortHorizonPredictor(tmp_path / "missing")

    result = predictor.predict_sides(
        symbol="EURUSD", quote_buffer=None, now_ts=1.0,
    )

    assert result["selected_side"] is None
    assert result["abstain"] is True
    assert result["prediction_reason"] == "artifact_not_found"
    assert set(result["side_predictions"]) == {"buy", "sell"}


def test_runtime_ev_uses_broker_native_usd_tick_value_for_jpy_pair(tmp_path: Path):
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
            SimpleNamespace(timestamp=1787659200.0, bid=150.00, ask=150.02),
            SimpleNamespace(timestamp=1787659201.0, bid=150.01, ask=150.03),
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
        "authorized_symbols": ["USDJPY"],
        "oos": {
            "sealed_by_symbol_horizon": {
                "USDJPY": {
                    "10": {
                        "mean_captured_exit_return": 0.0001,
                        "captured_exit_lcb95_return": 0.00005,
                    }
                }
            }
        },
    }

    result = predictor.predict(
        symbol="USDJPY",
        quote_buffer=SimpleNamespace(buffers={"USDJPY": Buffer()}),
        now_ts=1787659201.0,
        side="buy",
        broker_spec={
            "trade_tick_value": 1.0,
            "trade_tick_size": 0.01,
            "volume_min": 0.01,
        },
        quantity=0.01,
    )

    # 0.0001 relative return at ~150.02 is ~0.015 price units. With the
    # synthetic broker spec that is ~$0.015 at 0.01 lot, not 15 JPY mislabeled USD.
    assert result["expected_net_pnl"] < 0.1
    assert result["expected_net_pnl"] > 0.0
    assert result["expected_net_pnl_lcb95"] > 0.0


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


def test_execution_candidate_with_empty_authorization_rejects_every_symbol(tmp_path: Path):
    predictor = ShortHorizonPredictor(tmp_path / "missing")
    predictor.execution_status = "EXECUTION_CANDIDATE"
    predictor.status = "ready"
    predictor.metadata = {
        "target_definition": "captured_exit_replay",
        "authorized_symbols": [],
    }

    result = predictor.predict(symbol="EURUSD", quote_buffer=None, now_ts=1.0)

    assert result is not None
    assert result["abstain"] is True
    assert result["prediction_reason"] == "symbol_not_authorized"


def test_execution_candidate_does_not_fallback_to_global_oos_when_symbol_scope_missing(tmp_path: Path):
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
        "oos": {
            "sealed_by_horizon": {
                "10": {
                    "mean_captured_exit_return": 0.001,
                    "captured_exit_lcb95_return": 0.0005,
                }
            },
            "sealed_by_symbol_horizon": {},
        },
    }

    result = predictor.predict(
        symbol="EURUSD",
        quote_buffer=SimpleNamespace(buffers={"EURUSD": Buffer()}),
        now_ts=1787659201.0,
        broker_spec={
            "trade_tick_value": 1.0,
            "trade_tick_size": 0.0001,
            "volume_min": 0.01,
        },
        quantity=0.01,
    )

    assert result is not None
    assert result["abstain"] is True
    assert result["prediction_reason"] == "symbol_horizon_oos_missing"


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
