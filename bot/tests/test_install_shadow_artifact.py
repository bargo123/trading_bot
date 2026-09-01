from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.dummy import DummyClassifier

from scripts.install_shadow_artifact import install_shadow_artifact
from aegis.intel.short_horizon_runtime import ShortHorizonPredictor
from aegis.intel.short_horizon_policy import build_feature_provenance


def _artifact(path, *, feature_name: str = "bid"):
    path.mkdir()
    for name, constant in (("one", 0), ("two", 1)):
        estimator = DummyClassifier(strategy="constant", constant=constant)
        estimator.fit([[0.0], [1.0]], [0, 1])
        joblib.dump(estimator, path / f"{name}.runtime.joblib")
    try:
        provenance = build_feature_provenance([feature_name])
    except ValueError:
        provenance = {"schema": "invalid"}
    (path / "metadata.json").write_text(
        json.dumps(
            {
                "schema": "short_horizon_ensemble.v1",
                "execution_status": "SHADOW_ONLY_NO_POSITIVE_OOS",
                "dataset_hash": "dataset",
                "validation_hash": "validation",
                "horizons_s": [1],
                "oos_split_policy": {
                    "schema": "chronological_forward_horizon_purge.v1"
                },
                "feature_leakage_audit": {
                    "status": "PASS",
                    "future_aliases_found": []
                },
                "feature_provenance": provenance,
                "oos": {"sealed_by_horizon": {"1": {"n": 2}}},
                "feature_names": [feature_name],
                "models": [
                    {
                        "name": name,
                        "runtime_model_file": f"{name}.runtime.joblib",
                        "threshold": 0.5,
                        "metrics": {"calibration_status": "calibrated", "brier": 0.1},
                    }
                    for name in ("one", "two")
                ],
            }
        ),
        encoding="utf-8",
    )


def test_install_shadow_artifact_validates_and_quarantines_previous(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _artifact(source)
    _artifact(target)

    result = install_shadow_artifact(source, target)

    assert result["status"] == "shadow_only"
    assert result["execution_status"] == "SHADOW_ONLY_NO_POSITIVE_OOS"
    assert result["backup"]
    assert ShortHorizonPredictor(target).snapshot()["status"] == "shadow_only"
    assert ShortHorizonPredictor(target).snapshot()["model_count"] == 2
    assert Path(result["backup"]).is_dir()


def test_install_shadow_artifact_rejects_invalid_source_without_touching_target(tmp_path):
    source = tmp_path / "leaked"
    target = tmp_path / "target"
    _artifact(source, feature_name="time_to_first_net_green")
    _artifact(target)
    before = (target / "metadata.json").read_text(encoding="utf-8")

    try:
        install_shadow_artifact(source, target)
    except ValueError as exc:
        assert "not a valid shadow-only" in str(exc)
    else:
        raise AssertionError("invalid source unexpectedly installed")

    assert (target / "metadata.json").read_text(encoding="utf-8") == before
    assert not list(target.parent.glob(".target.staging-*"))
