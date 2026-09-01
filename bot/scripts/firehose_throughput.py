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
from typing import Iterable, Mapping

BOT = Path(__file__).resolve().parents[1]

SESSIONS = (("00", "07", "asia"), ("07", "12", "london"), ("12", "16", "london"),
            ("16", "21", "newyork"), ("21", "24", "asia"))
FUNNEL_STAGES = (
    "SCANS", "MICRO_CANDIDATES", "BOOK_SUPPORTED", "VALIDATED_MATCH",
    "EXPLORATION_ELIGIBLE", "SPREAD_REJECT", "ECONOMICS_REJECT",
    "GEOMETRY_REJECT", "RISK_REJECT", "STALE_REJECT", "OTHER_REJECT",
    "FIRES", "FILLS",
)
_TERMINAL_STAGES = set(FUNNEL_STAGES) - {"SCANS", "MICRO_CANDIDATES", "BOOK_SUPPORTED", "VALIDATED_MATCH", "EXPLORATION_ELIGIBLE", "FIRES", "FILLS"}


def session_of(ts: str) -> str:
    hour = ts[11:13] if len(ts) > 13 else ""
    for start, end, name in SESSIONS:
        if start <= hour < end:
            return name
    return "unknown"


def _funnel_terminal(reason: str) -> str:
    text = str(reason or "").lower()
    if "stale" in text or "future_quote" in text or "quote_refresh" in text:
        return "STALE_REJECT"
    if "spread" in text:
        return "SPREAD_REJECT"
    if "economics" in text or "expected" in text or "ev_" in text:
        return "ECONOMICS_REJECT"
    if "geometry" in text or "stop" in text or "target" in text:
        return "GEOMETRY_REJECT"
    if any(token in text for token in ("risk", "margin", "sizing", "lot", "position", "circuit", "halt")):
        return "RISK_REJECT"
    return "OTHER_REJECT"


def aggregate_funnel(rows: Iterable[Mapping]) -> dict[str, int]:
    """Aggregate truthful funnel rows without treating brain intent as a fire.

    Versioned ``firehose_funnel.v1`` rows are terminal per ``scan_id``; the
    last row wins when a scan moves from intent to a broker outcome. Legacy
    journal events are retained as a read-only compatibility path.
    """
    counts = {stage: 0 for stage in FUNNEL_STAGES}
    versioned: dict[str, Mapping] = {}
    legacy = []
    for row in rows:
        if str(row.get("event") or "") == "firehose_funnel.v1" and row.get("scan_id"):
            versioned[str(row["scan_id"])] = row
        else:
            legacy.append(row)

    for row in versioned.values():
        counts["SCANS"] += 1
        for field, stage in (
            ("micro_candidate_count", "MICRO_CANDIDATES"),
            ("book_supported", "BOOK_SUPPORTED"),
            ("validated_match", "VALIDATED_MATCH"),
            ("exploration_eligible", "EXPLORATION_ELIGIBLE"),
        ):
            value = row.get(field)
            if (isinstance(value, (int, float)) and value > 0) or value is True:
                counts[stage] += 1 if stage != "MICRO_CANDIDATES" else int(value)
        terminal = str(row.get("terminal") or "")
        if terminal in _TERMINAL_STAGES:
            counts[terminal] += 1
        if row.get("submitted") is True:
            counts["FIRES"] += 1
        if row.get("filled") is True:
            counts["FILLS"] += 1

    for row in legacy:
        event = str(row.get("event") or "")
        reason = str(row.get("reason") or row.get("msg") or "")
        if event in {"intel_brain_skip", "intel_brain_fire", "intel_brain_hold"}:
            counts["SCANS"] += 1
        if event == "intel_brain_fire":
            if row.get("exploration") or row.get("promotion_stage") == "EXPLORATION_CANARY":
                counts["EXPLORATION_ELIGIBLE"] += 1
            else:
                counts["VALIDATED_MATCH"] += 1
            if row.get("submitted") is True:
                counts["FIRES"] += 1
            if row.get("filled") is True:
                counts["FILLS"] += 1
        elif event == "intel_brain_skip":
            counts[_funnel_terminal(reason)] += 1
        elif event in {"margin_precheck_skip", "sizing_skip", "exploration_limit_skip", "halt", "hr_halt"}:
            counts["RISK_REJECT"] += 1
        elif event in {"spread_skip", "quote_spread_reject"}:
            counts["SPREAD_REJECT"] += 1
        elif event in {"quote_stale", "quote_future", "quote_refresh_failed", "quote_refresh_invalid"}:
            counts["STALE_REJECT"] += 1
        elif event == "oms_reject":
            counts[_funnel_terminal(reason)] += 1
        elif event == "order":
            if row.get("scan_id") and str(row["scan_id"]) in versioned:
                continue
            if row.get("submitted", True) is True:
                counts["FIRES"] += 1
            status = str(row.get("execution_status") or "")
            if row.get("filled") is True or status in {"POSITION_CONFIRMED", "DEAL_EXECUTED"}:
                counts["FILLS"] += 1
    return counts


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
    raw_rows: list[dict] = []

    with args.journal.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw_rows.append(row)
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
    truthful_funnel = aggregate_funnel(raw_rows)
    funnel.update(truthful_funnel)
    report = {
        "schema": "firehose_throughput.v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scanned_opportunities": brain_events,
        "eligible_opportunities": eligible,
        "fire_candidates": decisions["fire"],
        "scale_candidates": decisions["scale"],
        "funnel": dict(funnel),
        "truthful_funnel": truthful_funnel,
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
