"""Observed cost distributions from journals and deal snapshots. Never invent fills."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def cost_book_from_journal(path: Path) -> dict[str, Any]:
    rows = _read_jsonl(path)
    events = Counter(str(r.get("event") or "?") for r in rows)
    orders = [r for r in rows if r.get("event") == "order"]
    ok = [r for r in orders if r.get("ok")]
    no_money = [
        r
        for r in orders
        if not r.get("ok") and ("10019" in str(r.get("msg") or "") or "No money" in str(r.get("msg") or ""))
    ]
    spreads = []
    for row in rows:
        if row.get("spread") is None:
            continue
        try:
            spreads.append(float(row["spread"]))
        except (TypeError, ValueError):
            continue
    return {
        "schema": "costs.v1",
        "source": "journal",
        "n_events": len(rows),
        "n_orders": len(orders),
        "n_ok": len(ok),
        "n_no_money": len(no_money),
        "n_spread_skip": int(events.get("spread_skip", 0)),
        "events": dict(events),
        "spread_mean": (sum(spreads) / len(spreads)) if spreads else None,
        "commission_observed": False,
        "volume_kind": "broker_tick_volume_proxy",
    }


def pnl_summary(pnls: list[float]) -> dict[str, Any]:
    """Expectancy stats from observed PnL. Empty input is zeros, not invented fills."""
    n = len(pnls)
    if n == 0:
        return {
            "n": 0,
            "win_rate": None,
            "avg_win": None,
            "avg_loss": None,
            "expectancy": None,
            "profit_factor": None,
            "net_pnl": 0.0,
        }
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_win = float(sum(wins))
    gross_loss = float(abs(sum(losses)))
    return {
        "n": n,
        "win_rate": len(wins) / n,
        "avg_win": (gross_win / len(wins)) if wins else None,
        "avg_loss": (float(sum(losses)) / len(losses)) if losses else None,
        "expectancy": float(sum(pnls)) / n,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else None,
        "net_pnl": float(sum(pnls)),
    }


def cost_book_from_deals(path: Path) -> dict[str, Any]:
    rows = _read_jsonl(path)
    by_ticket: dict[str, dict[str, Any]] = {}
    untagged: list[dict[str, Any]] = []
    for row in rows:
        ticket = str(row.get("ticket") or "").strip()
        if ticket:
            by_ticket[ticket] = row
        else:
            untagged.append(row)
    unique = list(by_ticket.values()) + untagged
    pnls: list[float] = []
    commissions: list[float] = []
    swaps: list[float] = []
    for row in unique:
        try:
            pnls.append(float(row.get("pnl") or 0.0))
        except (TypeError, ValueError):
            continue
        try:
            commissions.append(float(row.get("commission") or 0.0))
        except (TypeError, ValueError):
            commissions.append(0.0)
        try:
            swaps.append(float(row.get("swap") or 0.0))
        except (TypeError, ValueError):
            swaps.append(0.0)
    commission_sum = float(sum(commissions))
    swap_sum = float(sum(swaps))
    stats = pnl_summary(pnls)
    return {
        "schema": "costs.v1",
        "source": "deals",
        "n_raw": len(rows),
        "n": stats["n"],
        "deduped_by": "ticket",
        "net_pnl": stats["net_pnl"],
        "win_rate": stats["win_rate"],
        "expectancy": stats["expectancy"],
        "profit_factor": stats["profit_factor"],
        "avg_win": stats["avg_win"],
        "avg_loss": stats["avg_loss"],
        "commission_sum": commission_sum,
        "swap_sum": swap_sum,
        "commission_mode": "observed_zero_or_absent",
        "commission_observed": commission_sum != 0.0,
    }


def summarize_symbol_costs(journal_rows: list[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    by_symbol: dict[str, dict[str, float]] = {}
    for row in journal_rows:
        if row.get("event") != "order":
            continue
        symbol = str(row.get("symbol") or "?")
        slot = by_symbol.setdefault(symbol, {"ok": 0.0, "fail": 0.0})
        if row.get("ok"):
            slot["ok"] += 1
        else:
            slot["fail"] += 1
    return by_symbol
