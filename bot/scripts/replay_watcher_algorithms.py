#!/usr/bin/env python3
"""Run the read-only Watcher algorithm replay over completed shadow rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.research.watcher_historical_replay import replay_jsonl  # noqa: E402
from aegis.research.registry import ExperimentRegistry  # noqa: E402


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return f"missing:{path.resolve()}"
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "reports" / "research" / "fast_edge_shadow_rows.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "reports" / "research" / "watcher_algorithm_historical_replay.json",
    )
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument(
        "--algorithm",
        action="append",
        dest="algorithm_names",
        help="bounded Watcher algorithm selection (repeatable; omit for legacy all-registry replay)",
    )
    parser.add_argument(
        "--rejection-rate",
        type=float,
        default=0.0,
        help="observed runner-wide rejection rate applied only to effective expectancy",
    )
    parser.add_argument(
        "--rejection-evidence",
        type=Path,
        help="JSON evidence metadata for the observed rejection rate",
    )
    parser.add_argument(
        "--split-ranges",
        type=Path,
        help="JSON object of half-open row-index split ranges, e.g. train/validation/test/sealed",
    )
    parser.add_argument("--purge-rows", type=int, default=0)
    parser.add_argument(
        "--pre-enriched",
        action="store_true",
        help="use the input row's already-generated causal features (sanitized; research-only)",
    )
    parser.add_argument(
        "--no-universe-context",
        action="store_true",
        help="omit expensive cross-symbol context when replaying a bounded selection",
    )
    parser.add_argument(
        "--reuse-same-quote-context",
        action="store_true",
        help="reuse derived causal context across rows sharing the same quote timestamp",
    )
    parser.add_argument(
        "--capture-execution-trace",
        action="store_true",
        help="persist a bounded, after-cost trace of selected causal signals",
    )
    parser.add_argument(
        "--execution-trace-limit",
        type=int,
        default=256,
        help="maximum after-cost trace rows per selected algorithm",
    )
    args = parser.parse_args(argv)
    rejection_evidence = None
    if args.rejection_evidence:
        try:
            loaded = json.loads(args.rejection_evidence.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid rejection evidence: {exc}") from exc
        if not isinstance(loaded, dict):
            raise SystemExit("invalid rejection evidence: expected JSON object")
        rejection_evidence = loaded
    split_ranges = None
    if args.split_ranges:
        try:
            loaded = json.loads(args.split_ranges.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"invalid split ranges: {exc}") from exc
        if not isinstance(loaded, dict):
            raise SystemExit("invalid split ranges: expected JSON object")
        split_ranges = {
            str(name): (int(bounds[0]), int(bounds[1]))
            for name, bounds in loaded.items()
        }
    report = replay_jsonl(
        args.input,
        max_rows=args.max_rows,
        algorithm_names=args.algorithm_names,
        split_ranges=split_ranges,
        purge_rows=args.purge_rows,
        rejection_rate=args.rejection_rate,
        rejection_evidence=rejection_evidence,
        pre_enriched=args.pre_enriched,
        include_universe_context=not args.no_universe_context,
        reuse_same_quote_context=args.reuse_same_quote_context,
        capture_execution_trace=args.capture_execution_trace,
        execution_trace_limit=args.execution_trace_limit,
    )
    # Bind the selected replay to the exact row file it consumed.  The
    # external-DAG manifest uses this provenance to prevent a stale replay
    # report from being paired with a newer shadow dataset.
    input_fingerprint = _file_sha256(args.input)
    report["input_dataset_sha256"] = input_fingerprint
    report["input_path"] = str(args.input.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    scope = f"rows={args.max_rows}" if args.max_rows is not None else "rows=all"
    selection_scope = "all" if args.algorithm_names is None else ",".join(args.algorithm_names)
    row_token = "all" if args.max_rows is None else str(args.max_rows)
    experiment_id = f"watcher_replay_{input_fingerprint[:16]}_{row_token}"
    registry = ExperimentRegistry()
    if registry.get(experiment_id) is None:
        registry.record(
            {
                "id": experiment_id,
                "hypothesis": "all registered GitHub-book Watcher algorithms preserve causal after-cost edge evidence",
                "status": "shadow" if report["rows_replayed"] else "failed",
                "code_commit": None,
                "config_fingerprint": f"watcher_algorithms_selected_v2:{scope}:{selection_scope}",
                "dataset_fingerprint": input_fingerprint,
                "provenance": {
                    "source": "watcher_algorithm_historical_replay",
                    "input_path": str(args.input),
                    "algorithm_count": report["algorithm_count"],
                    "book_count": report.get("book_coverage", {}).get("book_count"),
                },
                "params": {
                    "max_rows": args.max_rows,
                    "algorithm_names": args.algorithm_names,
                    "rejection_rate": args.rejection_rate,
                    "split_ranges": split_ranges,
                    "purge_rows": args.purge_rows,
                    "pre_enriched": args.pre_enriched,
                    "include_universe_context": not args.no_universe_context,
                    "reuse_same_quote_context": args.reuse_same_quote_context,
                },
                "metrics": {
                    "rows_replayed": report["rows_replayed"],
                    "rows_with_net_outcome": report["rows_with_net_outcome"],
                    "algorithm_count": report["algorithm_count"],
                },
                "rejection_reason": None if report["rows_replayed"] else "input_missing_or_empty",
            }
        )
    print(f"ROWS_REPLAYED={report['rows_replayed']}")
    print(f"ROWS_WITH_NET_OUTCOME={report['rows_with_net_outcome']}")
    print(f"ALGORITHMS={report['algorithm_count']}")
    print("ALGORITHM|SIGNAL_SAMPLES|WIN_RATE|EXPECTANCY|NET_PNL|P95_LOSS")
    for name, item in report["algorithms"].items():
        print("|".join([
            name,
            str(item["signal_samples"]),
            "-" if item["win_rate"] is None else f"{item['win_rate']:.6f}",
            "-" if item["expectancy"] is None else f"{item['expectancy']:.8f}",
            f"{item['net_pnl']:.8f}",
            "-" if item["p95_loss"] is None else f"{item['p95_loss']:.8f}",
        ]))
    print(f"EXACT_STRATEGIES={len(report.get('exact_strategies', {}))}")
    print(f"REPORT={args.output}")
    print(f"EXPERIMENT={experiment_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
