"""Install a validated shadow-only short-horizon artifact for the runner.

This utility never promotes an execution candidate.  It stages a complete
artifact, validates it through the same runtime loader used by the Firehose,
then swaps it into place while retaining the previous directory as a
recoverable quarantine copy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

if __package__ in {None, ""}:  # support ``python scripts/install_shadow_artifact.py``
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.intel.short_horizon_runtime import ShortHorizonPredictor


def _validated_shadow_snapshot(source: Path) -> dict[str, Any]:
    predictor = ShortHorizonPredictor(source)
    snapshot = predictor.snapshot()
    if snapshot.get("status") != "shadow_only":
        raise ValueError(
            "source artifact is not a valid shadow-only runtime artifact: "
            f"{snapshot.get('status')}:{snapshot.get('reason')}"
        )
    if snapshot.get("execution_status") == "EXECUTION_CANDIDATE":
        raise ValueError("shadow installer refuses execution candidates")
    if int(snapshot.get("model_count") or 0) < 2:
        raise ValueError("source artifact must contain at least two runtime models")
    audit = predictor.metadata.get("feature_leakage_audit")
    if not isinstance(audit, Mapping) or audit.get("status") != "PASS":
        raise ValueError("source artifact lacks a passing feature leakage audit")
    if audit.get("future_aliases_found") not in ([], None):
        raise ValueError("source artifact feature leakage audit contains aliases")
    split_policy = predictor.metadata.get("oos_split_policy")
    if not isinstance(split_policy, Mapping) or split_policy.get("schema") != (
        "chronological_forward_horizon_purge.v1"
    ):
        raise ValueError("source artifact lacks the chronological horizon purge policy")
    return snapshot


def install_shadow_artifact(
    source_path: Path,
    target_path: Path,
    *,
    backup_path: Path | None = None,
) -> dict[str, Any]:
    """Atomically install a validated shadow artifact and retain old files."""
    source = Path(source_path).resolve()
    target = Path(target_path).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"source artifact directory missing: {source}")
    if source == target:
        raise ValueError("source and target artifact directories must differ")

    source_snapshot = _validated_shadow_snapshot(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.staging-{os.getpid()}"
    if staging.exists():
        raise FileExistsError(f"staging path already exists: {staging}")
    shutil.copytree(source, staging)

    try:
        staged_snapshot = _validated_shadow_snapshot(staging)
        if staged_snapshot.get("dataset_hash") != source_snapshot.get("dataset_hash"):
            raise ValueError("staged artifact dataset hash changed during copy")

        backup: Path | None = None
        if target.exists():
            backup = (
                Path(backup_path).resolve()
                if backup_path is not None
                else target.parent
                / f"{target.name}.quarantine-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            )
            if backup.exists():
                raise FileExistsError(f"backup path already exists: {backup}")
            os.replace(target, backup)
        try:
            os.replace(staging, target)
        except Exception:
            if backup is not None and not target.exists():
                os.replace(backup, target)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return {
        "source": str(source),
        "target": str(target),
        "backup": str(backup) if backup is not None else None,
        "status": "shadow_only",
        "execution_status": source_snapshot.get("execution_status"),
        "dataset_hash": source_snapshot.get("dataset_hash"),
        "validation_hash": source_snapshot.get("validation_hash"),
        "model_count": source_snapshot.get("model_count"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--backup", type=Path, default=None)
    args = parser.parse_args()
    import json

    print(json.dumps(install_shadow_artifact(args.source, args.target, backup_path=args.backup), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
