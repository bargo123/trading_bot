"""Trend/market-structure algorithm inspired by Grimes, Brooks, and Volman."""
from __future__ import annotations
from ._common import absent, base, direction, side, strings, values, with_direction

ALGORITHM_ID = "trend_structure"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis", "Al Brooks — Reading Price Charts Bar by Bar", "Bob Volman — Forex Price Action Scalping")
KEYS = ("structure", "trend", "regime", "m15_trend", "h1_trend", "m15_context", "h1_context")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("structure_or_trend",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    directions = [direction(value) for _, value in found]
    directions = [value for value in directions if value]
    if directions and len(set(directions)) == 1:
        return with_direction(result, state, directions[0], "higher-high/lower-low and trend context agree")
    if "range" in strings(state, *KEYS):
        result["view"] = "WAIT"
        result["reasons"] = ["balanced or two-way range context"]
        return result
    result["view"] = "WAIT"
    result["reasons"] = ["structure and timeframe directions are mixed"]
    result["warnings"] = ["conflicting structure is not resolved by inventing a direction"]
    return result
