#!/usr/bin/env python3
"""Write read-only Firehose lifecycle evidence reports from an explicit JSONL journal."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.firehose_harvest_research import analyze_ticket_lifecycles, write_harvest_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", type=Path, required=True, help="Input JSONL lifecycle journal")
    parser.add_argument("--json-out", type=Path, required=True, help="Output JSON report path")
    parser.add_argument("--markdown-out", type=Path, required=True, help="Output Markdown report path")
    args = parser.parse_args()
    events = []
    with args.journal.open(encoding="utf-8") as journal:
        for line_number, line in enumerate(journal, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                parser.error(f"invalid JSONL at line {line_number}: {exc.msg}")
            if not isinstance(event, dict):
                parser.error(f"JSONL line {line_number} must be an object")
            events.append(event)
    write_harvest_report(analyze_ticket_lifecycles(events), args.json_out, args.markdown_out)


if __name__ == "__main__":
    main()
