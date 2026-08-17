"""Deterministic expected-value and payoff-quality metrics for the firehose brain.

This module is importable by the paper runner. It must never import the
research package. Win rate is reported; it never decides FIRE by itself.
"""
from __future__ import annotations

from statistics import mean
from typing import Any, Sequence

COSMETIC_BREAKEVEN_WR = 0.80
MAX_WINS_ERASED_BY_AVERAGE_LOSS = 4.0


def expected_net_value(
    *,
    p_win: float,
    expected_win: float,
    p_loss: float,
    expected_loss: float,
    expected_cost: float,
) -> float:
    """EV = P(win)×E[win] − P(loss)×E[loss] − costs. expected_loss is a magnitude."""
    return (
        float(p_win) * float(expected_win)
        - float(p_loss) * float(expected_loss)
        - float(expected_cost)
    )


def payoff_metrics(pnls: Sequence[float]) -> dict[str, Any]:
    """Describe whether wins are economically meaningful relative to losses.

    `wins_erased_by_average_loss` is how many average winners one average loser
    wipes out. CORE 1-pip TP / 30-pip SL is ~30. A 2R system is 0.5.
    """
    values = [float(value) for value in pnls]
    n = len(values)
    if n == 0:
        return {
            "n": 0,
            "n_wins": 0,
            "n_losses": 0,
            "win_rate": None,
            "avg_win": None,
            "avg_loss": None,
            "expectancy": None,
            "profit_factor": None,
            "net_pnl": 0.0,
            "payoff_ratio": None,
            "breakeven_wr": None,
            "wins_erased_by_average_loss": None,
            "wins_erased_by_tail_loss": None,
            "tail_loss": None,
            "cosmetic_win_rate": False,
        }
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_win = float(sum(wins))
    gross_loss = float(abs(sum(losses)))
    avg_win = mean(wins) if wins else None
    avg_loss = mean(losses) if losses else None
    tail_loss = abs(min(losses)) if losses else None
    erased_avg = (
        abs(avg_loss) / avg_win if avg_win and avg_loss is not None and avg_win > 0 else None
    )
    erased_tail = tail_loss / avg_win if avg_win and tail_loss and avg_win > 0 else None
    breakeven_wr = (
        abs(avg_loss) / (avg_win + abs(avg_loss))
        if avg_win and avg_loss is not None and (avg_win + abs(avg_loss)) > 0
        else None
    )
    expectancy = float(sum(values)) / n
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else None
    cosmetic = bool(
        (breakeven_wr is not None and breakeven_wr >= COSMETIC_BREAKEVEN_WR)
        or (
            erased_avg is not None
            and erased_avg >= MAX_WINS_ERASED_BY_AVERAGE_LOSS
        )
    )
    return {
        "n": n,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": len(wins) / n,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "net_pnl": float(sum(values)),
        "payoff_ratio": (avg_win / abs(avg_loss)) if avg_win and avg_loss else None,
        "breakeven_wr": breakeven_wr,
        "wins_erased_by_average_loss": erased_avg,
        "wins_erased_by_tail_loss": erased_tail,
        "tail_loss": tail_loss,
        "cosmetic_win_rate": cosmetic,
    }
