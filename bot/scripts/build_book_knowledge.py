#!/usr/bin/env python3
"""Build the structured book-knowledge base (master spec section A/L).

Deterministic, restart-safe ingestion of docs/trading/books/ into
bot/knowledge/*.jsonl + source_index.json + corpus_manifest.json.
Every source receives an explicit status; nothing is silently skipped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.research.book_knowledge import build_knowledge_base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build book knowledge base")
    parser.add_argument("--books", type=Path,
                        default=BOT.parent / "docs" / "trading" / "books")
    parser.add_argument("--out", type=Path, default=BOT / "knowledge")
    parser.add_argument("--force", action="store_true",
                        help="reprocess even unchanged files")
    args = parser.parse_args()

    if not args.books.is_dir():
        print(json.dumps({"error": f"books dir missing: {args.books}"}))
        return 1
    result = build_knowledge_base(args.books, args.out, force=args.force)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
