#!/usr/bin/env python3
"""Build a deduplicated, shadow-only reliability artifact from book replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aegis.research.book_reliability import build_book_reliability_artifact  # noqa: E402
from aegis.research.registry import ExperimentRegistry  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_artifact(
    replay_path: Path,
    output_path: Path,
    *,
    min_signal_samples: int = 50,
    min_losses: int = 5,
) -> dict[str, Any]:
    source = Path(replay_path)
    replay = json.loads(source.read_text(encoding="utf-8"))
    artifact = build_book_reliability_artifact(
        replay,
        min_signal_samples=min_signal_samples,
        min_losses=min_losses,
    )
    replay_hash = _sha256(source)
    artifact["source_replay_path"] = str(source)
    artifact["source_replay_sha256"] = replay_hash
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(artifact, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(temporary, destination)

    experiment_id = f"book_reliability_{replay_hash[:16]}_{min_signal_samples}_{min_losses}"
    registry = ExperimentRegistry()
    if registry.get(experiment_id) is None:
        registry.record(
            {
                "id": experiment_id,
                "hypothesis": "deduplicated book-rule reliability improves secondary ranking without authority",
                "status": "shadow",
                "code_commit": None,
                "config_fingerprint": f"book_reliability_v1:{min_signal_samples}:{min_losses}",
                "dataset_fingerprint": replay_hash,
                "provenance": {
                    "source": "book_strategy_historical_replay",
                    "replay_path": str(source),
                    "evaluator_group_count": artifact["evaluator_group_count"],
                },
                "params": {
                    "min_signal_samples": int(min_signal_samples),
                    "min_losses": int(min_losses),
                },
                "metrics": {
                    "book_record_count": artifact["book_record_count"],
                    "deduplicated_group_count": artifact["deduplicated_group_count"],
                    "candidate_count": artifact["candidate_count"],
                    "independent_split_status": artifact["independent_split_status"],
                    "independent_candidate_count": artifact["independent_candidate_count"],
                },
            }
        )
    return {
        "output": str(destination),
        "status": artifact["status"],
        "candidate_count": artifact["candidate_count"],
        "independent_split_status": artifact["independent_split_status"],
        "independent_candidate_count": artifact["independent_candidate_count"],
        "deduplicated_group_count": artifact["deduplicated_group_count"],
        "experiment_id": experiment_id,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-signal-samples", type=int, default=50)
    parser.add_argument("--min-losses", type=int, default=5)
    args = parser.parse_args(argv)
    print(json.dumps(build_artifact(
        args.replay_report,
        args.output,
        min_signal_samples=args.min_signal_samples,
        min_losses=args.min_losses,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
