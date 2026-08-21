#!/usr/bin/env python3
"""Fresh post-fix runtime report (audit fix 13).

Reads LIVE artifacts (heartbeat, journal tail, experiment store) and writes
bot/reports/research/exploration_fresh_report.json. No historical aggregates
are used as proof - everything here reflects the current process state.
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since-bar", default="2026-08-21 10:00",
                        help="journal window lower bound (post-fix)")
    parser.add_argument("--out", type=Path,
                        default=BOT / "reports" / "research" / "exploration_fresh_report.json")
    args = parser.parse_args()

    hb = json.loads((BOT / "reports" / "bot_heartbeat.json").read_text(encoding="utf-8"))
    store = json.loads((BOT / "intel" / "exploration_experiments.json").read_text(encoding="utf-8"))

    dist = collections.Counter()
    book_backed = 0
    for rec in store.get("experiments", {}).values():
        dist[str(rec.get("status"))] += 1
        if rec.get("book_logic"):
            book_backed += 1

    journal_counters: dict[str, int] = collections.Counter()
    last_inventory = None
    path = BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl"
    with path.open(encoding="utf-8", errors="replace") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 4_000_000))
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("bar") or "") < args.since_bar:
                continue
            ev = row.get("event")
            if ev == "exploration_limit_skip":
                journal_counters[f"skip:{str(row.get('reason'))[:44]}"] += 1
            elif ev == "intel_brain_fire" and row.get("exploration"):
                trig = str(row.get("exploration_trigger"))
                journal_counters[f"fire_trigger:{trig}"] += 1
                if row.get("book_logic"):
                    journal_counters["fires_with_book_logic"] += 1
            elif ev == "position_inventory":
                journal_counters["inventory_events"] += 1
                last_inventory = {
                    "positions": [
                        {k: p.get(k) for k in ("ticket", "symbol", "origin",
                                               "exploration", "hypothesis_id",
                                               "thesis_id", "legacy_unattributed",
                                               "client_comment")}
                        for p in row.get("positions", [])
                    ],
                    "unattributed_exploration": row.get("unattributed_exploration"),
                }
            elif ev == "pm_exit":
                journal_counters["pm_exit"] += 1
            elif ev == "pm_lock":
                journal_counters["pm_lock"] += 1

    # Economic claim inputs (honest): aggregate realized record remains as-is.
    econ_note = (
        "No validated profitable champion exists. Historical aggregate remains "
        "~n=2471 WR=67.83% PF=0.769 expectancy=-0.0110 net=-27.17."
    )

    report = {
        "schema": "exploration_fresh_report.v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "runner_pid": hb.get("pid"),
        "runner_status": hb.get("status"),
        "mt5_demo": True,
        "allow_live": False,
        "funnel": hb.get("funnel"),
        "pm_decisions": hb.get("profit_management", {}).get("decision_counts"),
        "pm_tickets": (hb.get("profit_management") or {}).get("tickets"),
        "exposure": hb.get("exposure"),
        "experiment_state_distribution": dict(dist),
        "book_backed_experiment_count": book_backed,
        "journal_since_fix": dict(journal_counters.most_common(20)),
        "last_position_inventory": last_inventory,
        "economic_claim": econ_note,
    }
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "out": str(args.out),
        "runner_pid": report["runner_pid"],
        "funnel_scans": (report["funnel"] or {}).get("scans"),
        "pm_decisions": report["pm_decisions"],
        "experiment_distribution": report["experiment_state_distribution"],
        "journal_since_fix": dict(list(journal_counters.most_common(8))),
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
