#!/usr/bin/env python3
"""Build a provenance-linked strategy registry from local book files."""
from __future__ import annotations

import argparse
from pathlib import Path

from aegis.research.book_strategy_extraction import build_strategy_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--downloads", type=Path, required=True, help="Directory containing PDF/DJVU source books")
    parser.add_argument("--output", type=Path, required=True, help="JSONL strategy registry output")
    parser.add_argument("--summary", type=Path, required=True, help="JSON extraction summary output")
    args = parser.parse_args(argv)
    summary = build_strategy_registry(args.downloads, args.output, summary_path=args.summary)
    print(f"SOURCES_SEEN={summary['sources_seen']}")
    print(f"SOURCES_UNIQUE={summary['sources_unique']}")
    print(f"PAGES_READ={summary['pages_read']}")
    print(f"RECORDS={summary['records']}")
    print(f"RECORDS_BY_STATUS={summary['records_by_status']}")
    print(f"DUPLICATE_COUNT={summary['duplicate_count']}")
    print(f"UNSUPPORTED_COUNT={summary['unsupported_count']}")
    print(f"OUTPUT={args.output}")
    print(f"SUMMARY={args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
