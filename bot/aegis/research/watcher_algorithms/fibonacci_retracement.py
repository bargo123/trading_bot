"""Observed-range Fibonacci retracement perspective."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "fibonacci_retracement"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "John F. Carter — Mastering the Trade",
)
KEYS = (
    "fib_retracement", "fib_retracement_zone", "fib_direction", "fib_236", "fib_382",
    "fib_500", "fib_618", "fib_786", "fib_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("observed_range_retracement",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    zone = strings(state, "fib_retracement_zone")
    trend = strings(state, "fib_direction")
    if trend == "up" and zone in {"0.382", "0.500", "0.618"}:
        return with_direction(result, state, "BUY", "upward observed-range retracement is in a commonly studied pullback zone")
    if trend == "down" and zone in {"0.382", "0.500", "0.618"}:
        return with_direction(result, state, "SELL", "downward observed-range retracement is in a commonly studied pullback zone")
    result["view"] = "WAIT"
    result["reasons"] = ["observed range is not at a directional retracement zone or lacks a confirmed trend"]
    return result
