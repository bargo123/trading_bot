"""Read-only $1,000/day gap calculation from recorded MT5 deal history."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def _deduped_deals(path: Path) -> list[dict[str, Any]]:
    """Mirror the existing ticket-dedup rule without manufacturing missing costs."""
    by_ticket: dict[str, dict[str, Any]] = {}
    untagged: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("source") != "mt5_deal":
            continue
        ticket = str(row.get("ticket") or "").strip()
        if ticket:
            by_ticket[ticket] = row
        else:
            untagged.append(row)
    return list(by_ticket.values()) + untagged


def calculate_thousand_day_gap(deals_path: Path, *, target_daily_usd: float = 1_000.0) -> dict[str, Any]:
    """Calculate the observed per-active-day PnL gap at reported deal quantity."""
    rows = _deduped_deals(Path(deals_path))
    daily: dict[str, float] = defaultdict(float)
    quantities: list[float] = []
    valid = 0
    for row in rows:
        try:
            pnl = float(row["pnl"])
            day = datetime.fromisoformat(str(row["ts"]).replace("Z", "+00:00")).date().isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        daily[day] += pnl
        valid += 1
        try:
            quantities.append(float(row.get("qty") or 0.0))
        except (TypeError, ValueError):
            pass
    active_days = sorted(daily)
    net = sum(daily.values())
    mean_daily = net / len(active_days) if active_days else None
    if active_days:
        first = datetime.fromisoformat(active_days[0]).date()
        last = datetime.fromisoformat(active_days[-1]).date()
        span_days = max(1, (last - first).days + 1)
    else:
        span_days = 0
    calendar_daily = net / span_days if span_days else None
    reported_qty = min(quantities) if quantities and len(set(quantities)) == 1 else None
    if mean_daily is None:
        size_conclusion = "unavailable: no parseable recorded deals"
        required_qty = None
    elif mean_daily <= 0:
        size_conclusion = "unsupported: observed daily expectancy is non-positive, so size-up cannot close the gap"
        required_qty = None
    elif reported_qty is None:
        size_conclusion = "unavailable: deal quantities vary, so linear size scaling is not defined"
        required_qty = None
    else:
        multiplier = target_daily_usd / mean_daily
        required_qty = reported_qty * multiplier
        size_conclusion = "linear scaling only; not a recommendation and ignores capacity, slippage, and margin"
    return {
        "label": "research_proxy",
        "source": str(deals_path),
        "deduped_by": "ticket",
        "n_trades": valid,
        "active_days": len(active_days),
        "span_days": span_days,
        "first_day": active_days[0] if active_days else None,
        "last_day": active_days[-1] if active_days else None,
        "net_pnl_usd": net,
        "mean_active_day_pnl_usd": mean_daily,
        "mean_calendar_day_pnl_usd": calendar_daily,
        "pip_ceiling_note": (
            "At 0.01 lots, majors are about $0.10 per pip. A $1,000/day target would need "
            "about 10,000 net pip-dollars/day after costs even with a perfect 1-pip hit rate. "
            "This is a size/geometry bound, not a forecast."
        ),
        "target_daily_usd": target_daily_usd,
        "reported_quantity": reported_qty,
        "required_quantity_if_linear": required_qty,
        "size_conclusion": size_conclusion,
        "capital_requirement": (
            "unavailable from deal history alone: broker margin, leverage, contract specs, "
            "and risk limits are required; no estimate is invented"
        ),
        "daily_pnl_usd": dict(sorted(daily.items())),
        "costs_note": (
            "Uses recorded deal PnL as provided. Commission/swap fields are not available "
            "in this snapshot, so this is not proof that every execution cost is captured."
        ),
    }


def markdown_thousand_day_gap(summary: dict[str, Any]) -> str:
    mean = summary["mean_active_day_pnl_usd"]
    mean_text = "unavailable" if mean is None else f"${mean:,.2f}"
    calendar = summary.get("mean_calendar_day_pnl_usd")
    calendar_text = "unavailable" if calendar is None else f"${calendar:,.2f}"
    qty = summary["required_quantity_if_linear"]
    qty_text = "not applicable" if qty is None else f"{qty:.4f} lots"
    return "\n".join(
        [
            "# $1,000/day gap snapshot",
            "",
            "Label: `research_proxy`. This is a read-only calculation from recorded MT5 deals, not a forecast or promotion.",
            "",
            f"- source: `{summary['source']}`",
            f"- ticket-deduped deals: {summary['n_trades']}",
            f"- active UTC days: {summary['active_days']} of {summary.get('span_days', summary['active_days'])} calendar days ({summary['first_day']} to {summary['last_day']})",
            f"- recorded net PnL: ${summary['net_pnl_usd']:,.2f}",
            f"- mean PnL per active day: {mean_text}",
            f"- mean PnL per calendar day: {calendar_text}",
            f"- pip/size bound: {summary.get('pip_ceiling_note', '')}",
            f"- target: ${summary['target_daily_usd']:,.2f}/day",
            f"- recorded quantity: {summary['reported_quantity'] if summary['reported_quantity'] is not None else 'mixed/unavailable'} lots",
            f"- required quantity if linear: {qty_text}",
            f"- size conclusion: {summary['size_conclusion']}",
            f"- capital: {summary['capital_requirement']}",
            f"- cost scope: {summary['costs_note']}",
            "",
            "No candidate is promoted. If observed expectancy is non-positive, increasing size cannot turn it positive.",
            "",
        ]
    )
