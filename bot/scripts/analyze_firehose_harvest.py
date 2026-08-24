#!/usr/bin/env python3
"""Write read-only Firehose lifecycle evidence reports from an explicit JSONL journal."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.firehose_harvest_research import (  # noqa: E402
    analyze_ticket_lifecycles,
    compare_exit_policies,
    write_harvest_report,
)


def read_jsonl(path: Path, parser: argparse.ArgumentParser) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                parser.error(f"invalid JSONL in {path} at line {line_number}: {exc.msg}")
            if not isinstance(row, dict):
                parser.error(f"JSONL in {path} at line {line_number} must be an object")
            rows.append(row)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True, help="Input JSONL lifecycle journal")
    parser.add_argument("--replay", type=Path, help="Optional costed OOS replay JSONL input")
    parser.add_argument("--json-out", type=Path, required=True, help="Output JSON report path")
    parser.add_argument("--markdown-out", type=Path, required=True, help="Output Markdown report path")
    args = parser.parse_args()
    report = analyze_ticket_lifecycles(read_jsonl(args.journal, parser))
    report["policy_comparison"] = compare_exit_policies(read_jsonl(args.replay, parser) if args.replay else [])
    write_harvest_report(report, args.json_out, args.markdown_out)


if __name__ == "__main__":
    main()
