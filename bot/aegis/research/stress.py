"""Monte Carlo and search-count correction. Never invents trade PnL."""
from __future__ import annotations

from typing import Sequence

import numpy as np


def bootstrap_expectancy(
    pnls: Sequence[float],
    *,
    n_boot: int = 2000,
    seed: int = 1,
) -> dict[str, float]:
    arr = np.asarray(list(pnls), dtype=float)
    if arr.size == 0:
        return {"n": 0.0, "mean": 0.0, "p05": 0.0, "p50": 0.0, "p95": 0.0, "frac_positive": 0.0}
    rng = np.random.default_rng(int(seed))
    draws = rng.choice(arr, size=(int(n_boot), arr.size), replace=True).mean(axis=1)
    return {
        "n": float(arr.size),
        "mean": float(arr.mean()),
        "p05": float(np.quantile(draws, 0.05)),
        "p50": float(np.quantile(draws, 0.50)),
        "p95": float(np.quantile(draws, 0.95)),
        "frac_positive": float((draws > 0).mean()),
    }


def holm_adjusted(pvalues: Sequence[float]) -> list[float]:
    """Holm step-down; used when many hypotheses were searched."""
    p = np.asarray(list(pvalues), dtype=float)
    m = len(p)
    if m == 0:
        return []
    order = np.argsort(p)
    adj = np.empty(m, dtype=float)
    running = 0.0
    for rank, idx in enumerate(order, start=1):
        val = min(1.0, p[idx] * (m - rank + 1))
        running = max(running, val)
        adj[idx] = running
    return [float(x) for x in adj]


def tail_stress(
    pnls: Sequence[float],
    *,
    worst_case_loss: float | None = None,
    extra_losses: int = 1,
) -> dict[str, float]:
    """Ask whether the edge survives one more bad trade.

    A tiny take-profit against a distant stop produces a high win rate long before
    the loss side is sampled. `worst_case_loss` lets the caller supply the stop the
    strategy actually risks, since the observed worst loss understates it when no
    stop-out happened in the window.
    """
    arr = np.asarray(list(pnls), dtype=float)
    if arr.size == 0:
        return {
            "n": 0.0,
            "n_losses": 0.0,
            "expectancy": 0.0,
            "worst_loss": 0.0,
            "expectancy_after_one_more_loss": 0.0,
        }
    losses = arr[arr < 0]
    observed_worst = float(-losses.min()) if losses.size else 0.0
    shock = float(worst_case_loss) if worst_case_loss is not None else observed_worst
    shock = max(shock, observed_worst)
    stressed = np.append(arr, [-abs(shock)] * max(0, int(extra_losses)))
    return {
        "n": float(arr.size),
        "n_losses": float(losses.size),
        "expectancy": float(arr.mean()),
        "worst_loss": observed_worst,
        "shock_loss": shock,
        "expectancy_after_one_more_loss": float(stressed.mean()),
    }


def family_wise_ok(p_raw: float, *, n_searches: int, alpha: float = 0.05) -> bool:
    if n_searches < 1:
        return False
    return float(p_raw) * int(n_searches) <= float(alpha)
