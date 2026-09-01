#!/usr/bin/env python3
"""Rebuild the research-only book coverage ledger. Never touches the MT5 runner."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
REPO = BOT.parent
sys.path.insert(0, str(BOT))

from aegis.research.book_audit import build_book_coverage, markdown_book_coverage  # noqa: E402
from aegis.research.fingerprint import config_fingerprint  # noqa: E402
from aegis.research.registry import DuplicateExperimentError, ExperimentRegistry  # noqa: E402
from aegis.research.thousand_day_gap import (  # noqa: E402
    calculate_thousand_day_gap,
    markdown_thousand_day_gap,
)


def _record_audit(ledger: dict, ledger_path: Path) -> str:
    payload_hash = hashlib.sha256(ledger_path.read_bytes()).hexdigest()
    registry = ExperimentRegistry()
    row = {
        "id": f"book_coverage_{payload_hash[:16]}",
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "hypothesis": "Full-book ledger reconciles on-disk extracts, catalog, notes, and index.",
        "status": "completed",
        "config_fingerprint": config_fingerprint(
            {"audit": "book_coverage", "schema_version": ledger["schema_version"]}
        ),
        "dataset_fingerprint": payload_hash,
        "params": {"label": "research_proxy", "strategy_implemented": False},
        "metrics": ledger["reconciliation"],
        "provenance": {
            "ledger": str(ledger_path),
            "claim": ledger["claim"],
            "mt5_touched": False,
            "placed_orders": False,
            "promoted_live_yaml": False,
        },
    }
    try:
        return registry.record(row)
    except DuplicateExperimentError:
        return row["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local trading-book extract coverage")
    parser.add_argument("--books-dir", type=Path, default=REPO / "docs" / "trading" / "books")
    parser.add_argument("--catalog", type=Path, default=REPO / "docs" / "trading" / "BOOKS_FULL.md")
    parser.add_argument("--notes-dir", type=Path, default=BOT / "research" / "source_notes")
    parser.add_argument("--index", type=Path, default=BOT / "research" / "books_index.sqlite")
    parser.add_argument("--ledger", type=Path, default=BOT / "research" / "book_coverage_ledger.json")
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "book_coverage.md")
    parser.add_argument("--deals", type=Path, default=BOT / "optimizer" / "metrics" / "trades.jsonl")
    parser.add_argument(
        "--gap-report", type=Path, default=BOT / "reports" / "research" / "thousand_day_gap.md"
    )
    args = parser.parse_args()

    ledger = build_book_coverage(
        books_dir=args.books_dir,
        catalog_path=args.catalog,
        index_path=args.index,
        notes_dir=args.notes_dir,
        ledger_path=args.ledger,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown_book_coverage(ledger), encoding="utf-8")
    gap = calculate_thousand_day_gap(args.deals)
    args.gap_report.parent.mkdir(parents=True, exist_ok=True)
    args.gap_report.write_text(markdown_thousand_day_gap(gap), encoding="utf-8")
    experiment_id = _record_audit(ledger, args.ledger)
    print(
        json.dumps(
            {
                "report": str(args.report),
                "ledger": str(args.ledger),
                "gap_report": str(args.gap_report),
                "experiment_id": experiment_id,
                "reconciliation": ledger["reconciliation"],
                "mt5_touched": False,
                "placed_orders": False,
                "promoted_live_yaml": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
