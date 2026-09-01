#!/usr/bin/env python3
"""Build/refresh the persistent book-memory knowledge system. Never touches MT5.

Compiles semantically validated knowledge records from `research/source_notes`
into `research/book_memory/` (JSONL + SQLite), then prints a quality summary.
Research-only and read-only with respect to trading state.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
REPO = BOT.parent
sys.path.insert(0, str(BOT))

from aegis.research.book_memory import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_NOTES_DIR,
    DEFAULT_RECORDS_PATH,
    BOOK_MEMORY_DIR,
    book_memory_summary,
    build_records_from_notes,
    build_sqlite_db,
    retrieve_knowledge,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the persistent book-memory knowledge system")
    parser.add_argument("--notes-dir", type=Path, default=DEFAULT_NOTES_DIR)
    parser.add_argument("--records", type=Path, default=DEFAULT_RECORDS_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "book_memory.json")
    args = parser.parse_args()

    records = build_records_from_notes(args.notes_dir, records_path=args.records)
    n = build_sqlite_db(args.records, args.db)
    summary = book_memory_summary()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    asia_sells = retrieve_knowledge(concept="range_edge_fade", limit=5)
    print(
        json.dumps(
            {
                "records": n,
                "dir": str(BOOK_MEMORY_DIR),
                "report": str(args.report),
                "with_entry": summary["n_with_entry"],
                "with_invalidation": summary["n_with_invalidation"],
                "top_concepts": list(summary["concepts"].items())[:8],
                "sample_retrieval_range_fade": len(asia_sells),
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