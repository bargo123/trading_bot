#!/usr/bin/env python3
"""Join broker exits to fast Firehose traces for research-only autopsy."""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT))

from aegis.intel.outcome_log import DEFAULT_OUTCOME_PATH  # noqa: E402
from aegis.research.outcome_learning import (  # noqa: E402
    read_outcomes,
    record_fast_trade_autopsy,
    summarize_fast_trade_autopsy,
)
from aegis.research.registry import ExperimentRegistry  # noqa: E402

DEFAULT_JOURNAL = BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl"
DEFAULT_REPORT = BOT / "reports" / "research" / "fast_trade_autopsy.json"
_EVENTS = frozenset({"firehose_open", "firehose_exit_trace", "pm_exit", "firehose_close"})


def _journal_events(path: Path, tickets: set[str]) -> dict[str, list[dict]]:
    events: dict[str, list[dict]] = defaultdict(list)
    if not path.is_file() or not tickets:
        return events
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("event") not in _EVENTS:
                continue
            ticket = str(event.get("ticket") or "")
            if ticket in tickets:
                events[ticket].append(event)
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Build fast-trade research autopsy")
    parser.add_argument("--log", type=Path, default=DEFAULT_OUTCOME_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL)
    parser.add_argument("--json", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    outcomes = [row for row in read_outcomes(args.log) if row.get("is_exit")]
    tickets = {
        identity
        for row in outcomes
        for identity in (str(row.get("ticket") or ""), str(row.get("position") or ""))
        if identity
    }
    summary = summarize_fast_trade_autopsy(outcomes, _journal_events(args.journal, tickets))
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    experiment_id = record_fast_trade_autopsy(summary, registry=ExperimentRegistry()) if summary["n_trades"] else None
    print(json.dumps({
        "json": str(args.json),
        "experiment_id": experiment_id,
        "n_trades": summary["n_trades"],
        "n_losses": summary["n_losses"],
        "n_wins": summary["n_wins"],
        "expectancy": (summary.get("metrics") or {}).get("expectancy"),
        "loss_categories": summary["loss_categories"],
        "mt5_touched": False,
        "placed_orders": False,
        "promoted_live_yaml": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
