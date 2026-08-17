"""Deterministic promotion gates. Win rate alone never promotes."""
from __future__ import annotations

from typing import Any


class GateReject(ValueError):
    """Challenger failed a required holdout gate."""


_MIN_TRADES = 20


def evaluate_promotion(
    metrics: dict[str, Any],
    champion: dict[str, Any] | None,
    *,
    min_trades: int = _MIN_TRADES,
) -> None:
    e = float(metrics.get("expectancy") or 0.0)
    if e <= 0:
        raise GateReject("holdout expectancy must be strictly positive")
    pf = metrics.get("profit_factor")
    if pf is None or float(pf) <= 1.0:
        raise GateReject("profit_factor must be strictly greater than 1")
    n = int(metrics.get("n_trades") or 0)
    if n < int(min_trades):
        raise GateReject(f"n_trades {n} below minimum {min_trades}")
    if champion is None:
        return
    champ_e = float(champion.get("expectancy") or 0.0)
    champ_pnl = float(champion.get("net_pnl") or 0.0)
    chal_pnl = float(metrics.get("net_pnl") or 0.0)
    if e <= champ_e or chal_pnl <= champ_pnl:
        raise GateReject("challenger must strictly beat champion on expectancy and net_pnl")
