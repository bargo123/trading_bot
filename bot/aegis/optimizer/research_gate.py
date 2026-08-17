"""Unattended optimizer must use research holdout gates. Cursor CLI stays off."""
from __future__ import annotations

from typing import Any

from aegis.research.gates import GateReject, evaluate_promotion

LIVE_VALID_SOURCES = frozenset({"mt5_bars"})


def research_overlay_gate(
    candidate_oos: dict[str, Any],
    *,
    data_source: str,
) -> tuple[bool, str]:
    """Reject synthetic/yahoo accepts and negative holdout E. Win rate is not enough."""
    src = str(data_source or "")
    if src not in LIVE_VALID_SOURCES:
        return False, f"data_source {src!r} is not live-valid MT5 bars (synthetic accepts are invalid)"
    wr = candidate_oos.get("win_rate")
    try:
        wr_f = float(wr or 0.0)
    except (TypeError, ValueError):
        wr_f = 0.0
    if wr_f > 1.0:
        wr_f = wr_f / 100.0
    metrics = {
        "expectancy": float(candidate_oos.get("expectancy_r") or candidate_oos.get("expectancy") or 0.0),
        "profit_factor": candidate_oos.get("profit_factor") or 0.0,
        "n_trades": int(candidate_oos.get("total_trades") or candidate_oos.get("n_trades") or 0),
        "net_pnl": float(candidate_oos.get("net_pnl") or 0.0),
        "win_rate": wr_f,
    }
    try:
        evaluate_promotion(metrics, champion=None)
    except GateReject as exc:
        return False, str(exc)
    return True, "research holdout gates passed (shadow; not live YAML)"
