"""Carver-style exponentially weighted moving-average crossover rule."""
from __future__ import annotations

from ._common import absent, base, first, number, values, with_direction

ALGORITHM_ID = "ewmac_trend_following"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Ernest P. Chan — Machine Trading",
)
KEYS = ("ewma_fast", "ewma_slow", "ewmac_fast_lookback", "ewmac_slow_lookback", "ewmac_forecast")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("ewma_crossover",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    fast = number(first(state, "ewma_fast"))
    slow = number(first(state, "ewma_slow"))
    fast_n = number(first(state, "ewmac_fast_lookback"))
    slow_n = number(first(state, "ewmac_slow_lookback"))
    if None in {fast, slow, fast_n, slow_n} or fast_n <= 0 or slow_n <= fast_n:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_fast_slow_ewma"]
        return result
    result["rule_parameters"] = {"fast_lookback": fast_n, "slow_lookback": slow_n}
    if fast > slow:
        return with_direction(result, state, "BUY", "fast EWMA is above the slow EWMA")
    if fast < slow:
        return with_direction(result, state, "SELL", "fast EWMA is below the slow EWMA")
    result["view"] = "WAIT"
    result["reasons"] = ["fast and slow EWMA are equal"]
    return result
