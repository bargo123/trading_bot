from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from scripts.migrate_runtime_model_artifact import migrate
from aegis.research_factory.ml_pipeline import MLPipeline, ModelConfig


def _frame(rows: int = 80) -> pd.DataFrame:
    target = np.tile([0, 1], rows // 2 + 1)[:rows]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=rows, freq="min", tz="UTC"),
            "return_1s": target + np.linspace(-0.2, 0.2, rows),
            "profit_barrier_first": target,
        }
    )


def test_migration_preserves_validation_metadata_and_adds_runtime_files(tmp_path):
    pipeline = MLPipeline(
        configs=[
            ModelConfig(
                name="logistic",
                model_type="logistic",
                params={"C": 1.0, "max_iter": 100},
                feature_selector=False,
                calibrate=False,
            )
        ]
    )
    frame = _frame()
    pipeline.train(frame.iloc[:60], frame.iloc[60:])
    pipeline.save(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update({"execution_status": "SHADOW_ONLY_NO_POSITIVE_OOS", "oos": {"sealed": {"n": 12}}})
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    for runtime_file in tmp_path.glob("*.runtime.joblib"):
        runtime_file.unlink()

    result = migrate(tmp_path)

    restored = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert result["execution_status"] == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert restored["execution_status"] == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert restored["oos"] == {"sealed": {"n": 12}}
    assert restored["runtime_format"] == "aegis.runtime_models.v1"
    assert all((tmp_path / name).is_file() for name in result["runtime_model_files"])


def test_migration_rejects_future_outcome_features_before_writing_runtime_files(tmp_path):
    pipeline = MLPipeline(
        configs=[
            ModelConfig(
                name="logistic",
                model_type="logistic",
                params={"C": 1.0, "max_iter": 100},
                feature_selector=False,
                calibrate=False,
            )
        ]
    )
    pipeline.train(_frame().iloc[:60], _frame().iloc[60:])
    pipeline.save(tmp_path)
    for runtime_file in tmp_path.glob("*.runtime.joblib"):
        runtime_file.unlink()
    metadata_path = tmp_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["feature_names"] = ["time_to_first_net_green"]
    metadata["models"][0]["feature_names"] = ["time_to_first_net_green"]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="future outcome alias"):
        migrate(tmp_path)

    assert not list(tmp_path.glob("*.runtime.joblib"))
