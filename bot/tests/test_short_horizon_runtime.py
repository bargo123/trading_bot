from pathlib import Path

import pandas as pd

from aegis.intel.short_horizon_runtime import (
    ShortHorizonPredictor,
    resample_runtime_quotes,
    seed_quote_buffer,
)


def test_short_horizon_runtime_is_fail_closed_without_artifact(tmp_path: Path):
    predictor = ShortHorizonPredictor(tmp_path / "missing")

    assert predictor.predict(symbol="EURUSD", quote_buffer=None, now_ts=1.0) is None
    assert predictor.snapshot()["status"] == "missing_artifact"
    assert predictor.snapshot()["reason"] == "artifact_not_found"


def test_short_horizon_runtime_rejects_non_short_horizon_metadata(tmp_path: Path):
    path = tmp_path / "model"
    path.mkdir()
    (path / "metadata.json").write_text('{"schema":"ml_pipeline.v1"}', encoding="utf-8")

    predictor = ShortHorizonPredictor(path)

    assert predictor.predict(symbol="EURUSD", quote_buffer=None, now_ts=1.0) is None
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
