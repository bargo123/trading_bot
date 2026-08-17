#!/usr/bin/env python3
"""Compile hashed book extracts into a research-only knowledge table."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.intel.paths import INTEL_DIR, ensure_intel_dirs  # noqa: E402
from aegis.research.books_index import BookIndex, discover_books_root  # noqa: E402
from aegis.research.knowledge import compile_from_index, write_knowledge_table  # noqa: E402
from aegis.research.paths import DEFAULT_BOOKS_INDEX, RESEARCH_DIR  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile book knowledge table (research-only)")
    parser.add_argument("--index", type=Path, default=DEFAULT_BOOKS_INDEX)
    parser.add_argument("--books-dir", type=Path)
    parser.add_argument("--notes-dir", type=Path, default=RESEARCH_DIR / "source_notes")
    parser.add_argument("--json", type=Path, default=INTEL_DIR / "knowledge_table.json")
    parser.add_argument("--report", type=Path, default=BOT / "reports" / "research" / "knowledge_table.md")
    args = parser.parse_args()
    ensure_intel_dirs()
    index = BookIndex(args.index)
    if args.books_dir is not None:
        index.rebuild(args.books_dir)
    elif not args.index.is_file() or not index.all_rows():
        books_dir = discover_books_root()
        if books_dir is None:
            raise SystemExit("no books directory and empty index")
        index.rebuild(books_dir)
    rows = compile_from_index(index, notes_dir=args.notes_dir)
    payload = write_knowledge_table(rows, json_path=args.json, markdown_path=args.report)
    print(
        json.dumps(
            {
                "n": payload["n"],
                "json": str(args.json),
                "report": str(args.report),
                "label": "research_proxy",
                "implemented": False,
                "placed_orders": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
