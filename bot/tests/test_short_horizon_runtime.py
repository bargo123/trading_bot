from pathlib import Path

from aegis.intel.short_horizon_runtime import ShortHorizonPredictor


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
