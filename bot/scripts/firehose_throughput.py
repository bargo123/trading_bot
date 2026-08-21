#!/usr/bin/env python3
"""Firehose throughput report (P7): where opportunities are lost.

Aggregates the runner journal into reports/research/firehose_throughput.json:
scanned opportunities, decision distribution, skip-reason distribution,
per-symbol and per-session distributions, order outcomes, quote refresh
counters. Read-only; cheap enough for the 20-min watcher.
"""
from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime, timezone
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
SESSIONS = (("00", "07", "asia"), ("07", "12", "london"), ("12", "16", "london"),
            ("16", "21", "newyork"), ("21", "24", "asia"))


def session_of(ts: str) -> str:
    hour = ts[11:13] if len(ts) > 13 else ""
    for start, end, name in SESSIONS:
        if start <= hour < end:
            return name
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description="Firehose throughput aggregation")
    parser.add_argument("--journal", type=Path,
                        default=BOT / "reports" / "mt5_demo_firehose_hw_journal.jsonl")
    parser.add_argument("--out", type=Path,
                        default=BOT / "reports" / "research" / "firehose_throughput.json")
    args = parser.parse_args()

    decisions = collections.Counter()
    skip_reasons = collections.Counter()
    by_symbol = collections.Counter()
    by_session = collections.Counter()
    fire_symbols = collections.Counter()
    orders = collections.Counter()
    reject_msgs = collections.Counter()
    brain_events = 0
    funnel = collections.Counter()

    with args.journal.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = row.get("event")
            bar = str(row.get("bar") or "")
            sym = str(row.get("symbol") or "?")
            if ev == "intel_brain_skip":
                brain_events += 1
                decisions["skip"] += 1
                reason = str(row.get("reason"))
                skip_reasons[reason] += 1
                by_symbol[sym] += 1
                by_session[session_of(bar)] += 1
            elif ev in {"intel_brain_fire", "intel_brain_scale", "intel_brain_reduce", "intel_brain_exit"}:
                brain_events += 1
                action = ev.replace("intel_brain_", "")
                decisions[action] += 1
                if action in {"fire", "scale"}:
                    fire_symbols[f"{sym}|{row.get('side')}"] += 1
                    shadow = row.get("shadow_action")
                    if shadow:
                        skip_reasons[f"shadow_suppressed:{action}"] += 1
                    # Funnel stage attribution (exploration vs validated).
                    if row.get("exploration") or row.get("promotion_stage") == "EXPLORATION_CANARY":
                        funnel["EXPLORATION_FIRE"] += 1
                    elif row.get("promotion_stage") == "DEMO_CANARY":
                        funnel["DEMO_CANARY"] += 1
                    elif row.get("promotion_stage") == "DEMO_CHAMPION":
                        funnel["CHAMPION_FIRE"] += 1
            elif ev == "order":
                orders["sent"] += 1
                if row.get("ok"):
                    orders["executed"] += 1
                    if str(row.get("client_tag") or "").startswith("EXP"):
                        funnel["EXPLORATION_EXECUTED"] += 1
                else:
                    orders["rejected"] += 1
                    reject_msgs[str(row.get("msg") or "")[:80]] += 1
            elif ev == "oms_reject":
                orders["oms_rejected"] += 1
                reject_msgs[f"oms:{row.get('reason')}"[:88]] += 1
            elif ev == "margin_precheck_skip":
                orders["margin_precheck_skip"] += 1
            elif ev == "sizing_skip" and row.get("reason") == "min_lot_broker":
                orders["min_lot_precheck_skip"] += 1

    eligible = decisions["fire"] + decisions["scale"] + decisions["skip"]
    report = {
        "schema": "firehose_throughput.v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scanned_opportunities": brain_events,
        "eligible_opportunities": eligible,
        "fire_candidates": decisions["fire"],
        "scale_candidates": decisions["scale"],
        "funnel": dict(funnel),
        "orders_sent": orders["sent"],
        "executed": orders["executed"],
        "rejected": orders["rejected"] + orders["oms_rejected"],
        "skip_rate": round(decisions["skip"] / eligible, 4) if eligible else None,
        "decisions": dict(decisions),
        "skip_reason_distribution": dict(skip_reasons.most_common(40)),
        "per_symbol_skips": dict(by_symbol.most_common(30)),
        "per_symbol_fires": dict(fire_symbols.most_common(30)),
        "per_session_skips": dict(by_session),
        "order_reject_messages": dict(reject_msgs.most_common(15)),
        "pretrade_guards": {
            k: v for k, v in orders.items() if k.startswith(("margin_precheck", "min_lot_precheck"))
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "scanned_opportunities", "fire_candidates", "scale_candidates",
        "skip_rate", "orders_sent", "executed", "rejected")}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
