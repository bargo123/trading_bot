"""Old Firehose vs Intelligent Firehose metrics from the demo journal."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from aegis.intel.expected_value import payoff_metrics


def load_journal(path: Path, *, tail: int = 12000) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    if tail > 0:
        lines = lines[-tail:]
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _pnls(rows: Sequence[Mapping[str, Any]], *, events: set[str], brains: set[str] | None = None) -> list[float]:
    out: list[float] = []
    for row in rows:
        if str(row.get("event") or "") not in events:
            continue
        if brains is not None:
            brain = str(row.get("brain") or "")
            if brains and brain not in brains and "intelligent" not in str(row.get("reason") or ""):
                if "intelligent" not in brain:
                    continue
        try:
            out.append(float(row["pnl"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def summarize_journal(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    actions = Counter(str(row.get("action") or "") for row in rows if str(row.get("event") or "").startswith("intel_brain"))
    skip_reasons = Counter(
        str(row.get("reason") or "")
        for row in rows
        if str(row.get("event") or "") == "intel_brain_skip"
    )
    intelligent_pnls = _pnls(rows, events={"flatten", "intel_brain_exit"}, brains={"intelligent_firehose"})
    # Intelligent exits journal intel_brain_exit; CORE still uses flatten/quick_win.
    core_pnls = [
        float(row["pnl"])
        for row in rows
        if str(row.get("event") or "") == "flatten"
        and str(row.get("reason") or "") in {"quick_win", "max_hold", "giveback"}
        and "pnl" in row
    ]
    intel_closed = [
        float(row["pnl"])
        for row in rows
        if str(row.get("event") or "") in {"intel_brain_exit", "intel_brain_reduce"}
        and "pnl" in row
    ]
    core_stats = payoff_metrics(core_pnls)
    intel_stats = payoff_metrics(intel_closed)
    fires = sum(1 for row in rows if str(row.get("event") or "") == "intel_brain_fire")
    return {
        "schema": "old_vs_intelligent.v1",
        "old": {
            "closes": int(core_stats["n"]),
            "win_rate": core_stats.get("win_rate"),
            "net_pnl": core_stats.get("net_pnl"),
            "expectancy": core_stats.get("expectancy"),
            "profit_factor": core_stats.get("profit_factor"),
            "avg_win": core_stats.get("avg_win"),
            "avg_loss": core_stats.get("avg_loss"),
            "payoff_ratio": core_stats.get("payoff_ratio"),
            "cosmetic_win_rate": core_stats.get("cosmetic_win_rate"),
            "wins_erased_by_average_loss": core_stats.get("wins_erased_by_average_loss"),
            "tail_loss": core_stats.get("tail_loss"),
        },
        "intelligent": {
            "fires": fires,
            "scales": int(actions.get("scale", 0)),
            "holds": int(actions.get("hold", 0)),
            "reduces": int(actions.get("reduce", 0)),
            "exits": int(actions.get("exit", 0)),
            "skips": int(actions.get("skip", 0)),
            "closes": int(intel_stats["n"]),
            "win_rate": intel_stats.get("win_rate"),
            "net_pnl": intel_stats.get("net_pnl"),
            "expectancy": intel_stats.get("expectancy"),
            "profit_factor": intel_stats.get("profit_factor"),
            "avg_win": intel_stats.get("avg_win"),
            "avg_loss": intel_stats.get("avg_loss"),
            "payoff_ratio": intel_stats.get("payoff_ratio"),
            "cosmetic_win_rate": intel_stats.get("cosmetic_win_rate"),
            "wins_erased_by_average_loss": intel_stats.get("wins_erased_by_average_loss"),
            "tail_loss": intel_stats.get("tail_loss"),
            "top_skip_reasons": skip_reasons.most_common(8),
        },
        "target_gap": {
            "objective_usd_per_day": 100.0,
            "claim": "not_reached_unless_measured_net_is_positive_and_stable",
            "formula": "positive_edge * opportunities * healthy_payoff * appropriate_capital",
        },
    }


def scoreboard_markdown(summary: Mapping[str, Any]) -> str:
    old = summary.get("old") or {}
    new = summary.get("intelligent") or {}
    lines = [
        "# Old Firehose vs Intelligent Firehose",
        "",
        "Educational demo metrics. Not a profit guarantee. $100/day is a gap target, not a claim.",
        "",
        "## Old Firehose (CORE flatten / 1-pip heritage)",
        "",
        f"- closes: {old.get('closes')}",
        f"- win_rate: {old.get('win_rate')}",
        f"- net_pnl: {old.get('net_pnl')}",
        f"- expectancy: {old.get('expectancy')}",
        f"- profit_factor: {old.get('profit_factor')}",
        f"- avg_win: {old.get('avg_win')}",
        f"- avg_loss: {old.get('avg_loss')}",
        f"- cosmetic_win_rate: {old.get('cosmetic_win_rate')}",
        f"- wins_erased_by_average_loss: {old.get('wins_erased_by_average_loss')}",
        "",
        "## Intelligent Firehose",
        "",
        f"- fires: {new.get('fires')}",
        f"- scales: {new.get('scales')}",
        f"- holds: {new.get('holds')}",
        f"- reduces: {new.get('reduces')}",
        f"- exits: {new.get('exits')}",
        f"- skips: {new.get('skips')}",
        f"- closes: {new.get('closes')}",
        f"- win_rate: {new.get('win_rate')}",
        f"- net_pnl: {new.get('net_pnl')}",
        f"- expectancy: {new.get('expectancy')}",
        f"- profit_factor: {new.get('profit_factor')}",
        f"- avg_win: {new.get('avg_win')}",
        f"- avg_loss: {new.get('avg_loss')}",
        f"- cosmetic_win_rate: {new.get('cosmetic_win_rate')}",
        f"- top_skip_reasons: {new.get('top_skip_reasons')}",
        "",
        "## $100/day gap",
        "",
        "- Do not increase lots to force the target.",
        "- Close the gap only with verified edge, enough independent opportunities, healthy payoff, and more capital at the same risk fraction.",
        "",
    ]
    return "\n".join(lines)
