"""Outcome-learning consumer for the Intelligent Firehose.

Reads `intel/outcome_log.jsonl` (write-only until now) and turns reconciled
exits into structured evidence: scoreboard metrics, payoff geometry, and
per-dimension slices. It observes; it never places orders and never mutates
trading state.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from aegis.intel.expected_value import payoff_metrics
from aegis.research.costs import pnl_summary

DEFAULT_OUTCOME_PATH = Path(__file__).resolve().parents[2] / "intel" / "outcome_log.jsonl"


def read_outcomes(path: Path | None = None) -> list[dict[str, Any]]:
    """Read and deduplicate outcome rows by ticket identity.

    Reconciliation writes one row per deal ticket. A duplicated row (e.g. from
    a cursor reset) must not double-count PnL, so we keep the first occurrence.
    """
    target = Path(path) if path is not None else DEFAULT_OUTCOME_PATH
    if not target.is_file():
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        ticket = str(payload.get("ticket") or "")
        if ticket and ticket != "0":
            if ticket in seen:
                continue
            seen.add(ticket)
        rows.append(payload)
    return rows


def exit_pnls(rows: Iterable[Mapping[str, Any]]) -> list[float]:
    out: list[float] = []
    for row in rows:
        if not row.get("is_exit"):
            continue
        try:
            out.append(float(row["pnl"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def slice_learning(
    rows: Iterable[Mapping[str, Any]],
    *,
    by: tuple[str, ...] = ("symbol", "side", "close_reason"),
) -> list[dict[str, Any]]:
    """Slice exit PnL by context dimensions; ranked by net PnL."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if not row.get("is_exit"):
            continue
        try:
            pnl = float(row["pnl"])
        except (KeyError, TypeError, ValueError):
            continue
        key = "|".join(str(row.get(field) or "unknown") for field in by)
        buckets[key].append(pnl)
    ranked = sorted(
        (
            {"key": key, "by": list(by), **payoff_metrics(values)}
            for key, values in buckets.items()
            if len(values) >= 5
        ),
        key=lambda item: float(item.get("expectancy") or -1e18),
        reverse=True,
    )
    return ranked


def summarize_outcomes(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Full learning summary over reconciled exit rows."""
    rows = list(rows)
    exits = [row for row in rows if row.get("is_exit")]
    pnls = exit_pnls(exits)
    metrics = payoff_metrics(pnls)
    by_symbol = slice_learning(exits, by=("symbol",))
    by_side = slice_learning(exits, by=("side",))
    by_reason = slice_learning(exits, by=("close_reason",))
    by_symbol_side = slice_learning(exits, by=("symbol", "side"))
    return {
        "schema": "outcome_learning.v1",
        "label": "research_proxy",
        "n_rows": len(rows),
        "n_exits": len(exits),
        "metrics": metrics,
        "by_symbol": by_symbol,
        "by_side": by_side,
        "by_close_reason": by_reason,
        "by_symbol_side": by_symbol_side,
    }


def outcome_learning_markdown(summary: Mapping[str, Any]) -> str:
    m = summary.get("metrics") or {}
    lines = [
        "# Outcome learning (reconciled exits)",
        "",
        "Label: `research_proxy`. Observed demo outcomes; not a profit guarantee.",
        "",
        f"- rows: {summary.get('n_rows')}",
        f"- exits: {summary.get('n_exits')}",
        "",
        "## Payoff geometry",
        "",
        f"- win_rate: {m.get('win_rate')}",
        f"- expectancy: {m.get('expectancy')}",
        f"- profit_factor: {m.get('profit_factor')}",
        f"- avg_win: {m.get('avg_win')}",
        f"- avg_loss: {m.get('avg_loss')}",
        f"- payoff_ratio: {m.get('payoff_ratio')}",
        f"- wins_erased_by_average_loss: {m.get('wins_erased_by_average_loss')}",
        f"- wins_erased_by_tail_loss: {m.get('wins_erased_by_tail_loss')}",
        f"- tail_loss: {m.get('tail_loss')}",
        f"- cosmetic_win_rate: {m.get('cosmetic_win_rate')}",
        "",
        "## By symbol",
        "",
    ]
    for row in (summary.get("by_symbol") or [])[:12]:
        lines.append(
            f"- {row['key']}: n={row['n']} exp={row['expectancy']} PF={row['profit_factor']} "
            f"erase_avg={row['wins_erased_by_average_loss']}"
        )
    lines += ["", "## By side", ""]
    for row in (summary.get("by_side") or []):
        lines.append(f"- {row['key']}: n={row['n']} exp={row['expectancy']} PF={row['profit_factor']}")
    lines += ["", "## By close reason", ""]
    for row in (summary.get("by_close_reason") or []):
        lines.append(
            f"- {row['key']}: n={row['n']} exp={row['expectancy']} PF={row['profit_factor']}"
        )
    return "\n".join(lines)