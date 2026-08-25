from pathlib import Path

from aegis.intel.short_horizon_runtime import ShortHorizonPredictor, seed_quote_buffer


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
