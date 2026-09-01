"""Add factory-independent raw estimator files to an existing model artifact.

The migration copies the already-trained estimator objects only.  It preserves
all validation, OOS, and promotion metadata; it never retrains or promotes a
model.  The Research Factory import is intentionally confined to this offline
utility, not the Firehose runtime.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import os
import sys

import joblib

BOT_ROOT = Path(__file__).resolve().parents[1]
if str(BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(BOT_ROOT))

from aegis.research_factory.ml_pipeline import MLPipeline
from aegis.research.short_horizon_artifact import validate_point_in_time_feature_names
from aegis.intel.short_horizon_policy import build_feature_provenance


def migrate(artifact_path: Path) -> dict[str, object]:
    root = Path(artifact_path).resolve()
    metadata_path = root / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("artifact metadata must be an object")
    pipeline = MLPipeline.load(root)
    if not pipeline.models:
        raise ValueError("artifact has no legacy models")

    metadata_models = metadata.get("models")
    if not isinstance(metadata_models, list):
        raise ValueError("artifact metadata models must be a list")
    # Validate the complete feature contract before creating any runtime
    # files.  A migrated artifact is still runtime input, so a legacy model
    # containing a post-entry outcome alias must fail closed here as well as in
    # the Firehose loader.
    feature_names = metadata.get("feature_names") or ()
    validate_point_in_time_feature_names(feature_names)
    for row in metadata_models:
        if isinstance(row, dict):
            validate_point_in_time_feature_names(row.get("feature_names") or ())
    metadata["feature_provenance"] = build_feature_provenance(feature_names)
    rows_by_name = {
        str(row.get("name") or ""): row
        for row in metadata_models
        if isinstance(row, dict)
    }
    runtime_files: list[str] = []
    for model in pipeline.models:
        row = rows_by_name.get(str(model.name))
        if row is None:
            raise ValueError(f"model metadata missing: {model.name}")
        runtime_file = f"{model.name}.runtime.joblib"
        joblib.dump(model.model, root / runtime_file)
        row["feature_names"] = list(model.feature_names)
        row["runtime_model_file"] = runtime_file
        runtime_files.append(runtime_file)

    metadata["runtime_format"] = "aegis.runtime_models.v1"
    metadata["runtime_model_files"] = runtime_files
    temporary = metadata_path.with_name(f".{metadata_path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    os.replace(temporary, metadata_path)
    return {
        "artifact": str(root),
        "runtime_model_files": runtime_files,
        "execution_status": metadata.get("execution_status"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.artifact), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
