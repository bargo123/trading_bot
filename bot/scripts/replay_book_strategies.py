#!/usr/bin/env python3
"""Run the read-only chronological replay for every testable book record."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.research.book_strategy_replay import iter_jsonl, replay_jsonl  # noqa: E402
from aegis.research.registry import ExperimentRegistry  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _split_ranges_for_rows(
    row_path: Path,
    *,
    ratios: tuple[float, float, float],
    max_rows: int | None,
    purge_seconds: float | None = None,
) -> dict[str, tuple[int, int]]:
    """Convert ratios into disjoint chronological ranges with an optional purge."""
    if len(ratios) != 3 or any(value <= 0 for value in ratios):
        raise ValueError("split ratios must contain three positive values")
    rows: list[dict[str, Any]] = []
    for row in iter_jsonl(row_path):
        rows.append(row)
        if max_rows is not None and len(rows) >= max_rows:
            break
    total = len(rows)
    if total < 3:
        raise ValueError("at least three rows are required for split replay")
    denominator = sum(ratios)
    first = max(1, min(total - 2, int(total * ratios[0] / denominator)))
    second = max(first + 1, min(total - 1, first + int(total * ratios[1] / denominator)))
    base_ranges = {
        "train": (0, first),
        "validation": (first, second),
        "sealed": (second, total),
    }
    if purge_seconds is None:
        horizons = []
        for row in rows:
            if "horizon_s" not in row or row.get("horizon_s") is None:
                continue
            try:
                value = float(row.get("horizon_s"))
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("horizon_s must be finite and non-negative") from exc
            if not math.isfinite(value) or value < 0.0:
                raise ValueError("horizon_s must be finite and non-negative")
            horizons.append(value)
        purge_seconds = max(horizons, default=0.0)
    try:
        purge = float(purge_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("purge seconds must be finite and non-negative") from exc
    if not math.isfinite(purge) or purge < 0.0:
        raise ValueError("purge seconds must be finite and non-negative")
    if purge == 0.0:
        return base_ranges

    def timestamp_seconds(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = float(value)
            return result if math.isfinite(result) else None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()

    times = [timestamp_seconds(row.get("time")) for row in rows]
    if any(value is None for value in times):
        raise ValueError("purged split ranges require valid timestamps")
    numeric_times = [float(value) for value in times]
    if any(later < earlier for earlier, later in zip(numeric_times, numeric_times[1:])):
        raise ValueError("purged split ranges require chronological rows")

    def first_after(index: int) -> int:
        cutoff = numeric_times[index - 1] + purge
        cursor = index
        while cursor < total and numeric_times[cursor] <= cutoff:
            cursor += 1
        return cursor

    validation_start = first_after(first)
    sealed_start = first_after(second)
    if validation_start >= second or sealed_start >= total:
        raise ValueError("purge leaves an empty split")
    return {
        "train": (0, first),
        "validation": (validation_start, second),
        "sealed": (sealed_start, total),
    }


def _max_label_horizon_seconds(
    row_path: Path, *, max_rows: int | None
) -> float:
    """Read the maximum finite forward label horizon for split provenance."""
    maximum = 0.0
    for index, row in enumerate(iter_jsonl(row_path)):
        if max_rows is not None and index >= max_rows:
            break
        if "horizon_s" not in row or row.get("horizon_s") is None:
            continue
        try:
            value = float(row.get("horizon_s"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("horizon_s must be finite and non-negative") from exc
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("horizon_s must be finite and non-negative")
        maximum = max(maximum, value)
    return maximum


def record_replay_experiment(
    report: dict[str, Any],
    strategy_path: Path,
    input_path: Path,
    *,
    max_rows: int | None,
    pre_enriched_rows: bool = False,
    registry_path: Path | None = None,
) -> str:
    """Persist one immutable book replay run and return its deterministic id."""
    strategy_hash = _sha256(strategy_path)
    input_hash = _sha256(input_path)
    row_token = "all" if max_rows is None else str(max_rows)
    if pre_enriched_rows:
        row_token += "_pre_enriched"
    purge_seconds = report.get("split_replay_purge_seconds")
    if purge_seconds is not None:
        try:
            row_token += f"_purge{float(purge_seconds):g}"
        except (TypeError, ValueError, OverflowError):
            row_token += "_purge_invalid"
    dataset_fingerprint = hashlib.sha256(
        f"{strategy_hash}:{input_hash}:{row_token}".encode("utf-8")
    ).hexdigest()
    experiment_id = f"book_replay_{dataset_fingerprint[:16]}_{row_token}"
    registry = ExperimentRegistry(registry_path)
    if registry.get(experiment_id) is None:
        registry.record(
            {
                "id": experiment_id,
                "hypothesis": "testable book strategies preserve causal after-cost evidence",
                "status": "shadow" if report.get("rows_replayed") else "failed",
                "code_commit": None,
                "config_fingerprint": f"book_strategy_replay_v1:{row_token}",
                "dataset_fingerprint": dataset_fingerprint,
                "provenance": {
                    "source": "book_strategy_historical_replay",
                    "strategy_path": str(strategy_path),
                    "input_path": str(input_path),
                    "strategy_sha256": strategy_hash,
                    "input_sha256": input_hash,
                },
                "params": {
                    "max_rows": max_rows,
                    "pre_enriched_rows": bool(pre_enriched_rows),
                    "split_replay_purge_seconds": purge_seconds,
                },
                "metrics": {
                    "rows_replayed": report.get("rows_replayed", 0),
                    "rows_with_net_outcome": report.get("rows_with_net_outcome", 0),
                    "book_record_count": report.get("book_record_count", 0),
                    "testable_record_count": report.get("testable_record_count", 0),
                    "evaluator_group_count": report.get("evaluator_group_count", 0),
                },
                "rejection_reason": None if report.get("rows_replayed") else "input_missing_or_empty",
            }
        )
    return experiment_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strategies",
        type=Path,
        default=ROOT / "reports" / "research" / "book_strategy_registry.jsonl",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "reports" / "research" / "fast_edge_shadow_rows.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "research" / "book_strategy_historical_replay.json",
    )
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument(
        "--split-ratios",
        type=float,
        nargs=3,
        metavar=("TRAIN", "VALIDATION", "SEALED"),
        default=None,
        help="emit disjoint chronological train/validation/sealed group evidence",
    )
    parser.add_argument(
        "--purge-seconds",
        type=float,
        default=None,
        help="embargo split starts by this many seconds; defaults to max row horizon",
    )
    parser.add_argument(
        "--pre-enriched-rows",
        action="store_true",
        help="use causally precomputed row features after outcome/future sanitization",
    )
    args = parser.parse_args(argv)
    split_ranges = None
    split_purge_seconds = None
    if args.split_ratios is not None:
        split_purge_seconds = (
            float(args.purge_seconds)
            if args.purge_seconds is not None
            else _max_label_horizon_seconds(args.input, max_rows=args.max_rows)
        )
        split_ranges = _split_ranges_for_rows(
            args.input,
            ratios=tuple(args.split_ratios),
            max_rows=args.max_rows,
            purge_seconds=split_purge_seconds,
        )
    report = replay_jsonl(
        args.strategies,
        args.input,
        max_rows=args.max_rows,
        split_ranges=split_ranges,
        pre_enriched_rows=args.pre_enriched_rows,
    )
    if split_ranges:
        report["split_replay_purge_seconds"] = split_purge_seconds
        report["split_replay_policy"] = "chronological_forward_horizon_purge.v1"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    experiment_id = record_replay_experiment(
        report,
        args.strategies,
        args.input,
        max_rows=args.max_rows,
        pre_enriched_rows=args.pre_enriched_rows,
    )
    print(f"ROWS_REPLAYED={report['rows_replayed']}")
    print(f"BOOK_RECORDS={report['book_record_count']}")
    print(f"TESTABLE_RECORDS={report['testable_record_count']}")
    print(f"EVALUATOR_GROUPS={report['evaluator_group_count']}")
    print(f"IMPLEMENTATION_COUNTS={report['implementation_counts']}")
    if split_ranges:
        print(f"SPLIT_RANGES={report['split_replay_ranges']}")
        print(
            "SPLIT_ROWS="
            + str({name: value["rows_replayed"] for name, value in report["split_replay"].items()})
        )
    print(f"REPORT={args.output}")
    print(f"EXPERIMENT={experiment_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
