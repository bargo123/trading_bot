"""Fresh-quote short-horizon scalping algorithm."""
from __future__ import annotations
from ._common import base, direction, first, number, strings, values, with_direction

ALGORITHM_ID = "scalping_execution"
SOURCES = ("Bob Volman — Forex Price Action Scalping", "Irene Aldridge — High-Frequency Trading", "Barry Johnson — Algorithmic Trading and DMA", "Michel Dacorogna — An Introduction to High-Frequency Finance")
KEYS = ("spread_pips", "quote_age_s", "quote_fresh", "horizon_s", "tick_velocity", "tick_direction", "short_returns", "entry")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("quote_horizon_and_tick_state",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    age = number(first(state, "quote_age_s"))
    if first(state, "quote_fresh") is False or (age is not None and age > 5):
        result["view"] = "WAIT"
        result["reasons"] = ["short-horizon quote is not fresh enough for a scalp"]
        return result
    signal = direction(strings(state, "tick_direction", "short_returns"))
    if signal:
        return with_direction(result, state, signal, "fresh tick direction or short-return persistence is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["fresh quote exists but short-horizon direction is unresolved"]
    return result
