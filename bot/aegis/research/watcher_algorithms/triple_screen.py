"""Elder's three-screen trend, correction, and trigger framework."""
from __future__ import annotations

from ._common import absent, base, direction, first, strings, values, with_direction

ALGORITHM_ID = "triple_screen"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = ("primary_trend", "intermediate_oscillator", "short_trigger")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("three_screen_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    primary = direction(first(state, "primary_trend"))
    trigger = direction(first(state, "short_trigger"))
    intermediate = strings(state, "intermediate_oscillator")
    if primary is None or trigger is None:
        result["view"] = "WAIT"
        result["reasons"] = ["primary trend and short-screen trigger must both have a direction"]
        return result
    if primary != trigger:
        result["view"] = "WAIT"
        result["reasons"] = ["short-screen trigger conflicts with the primary trend"]
        return result
    correction_ok = (
        primary == "BUY" and any(token in intermediate for token in ("oversold", "recovery", "pullback"))
    ) or (
        primary == "SELL" and any(token in intermediate for token in ("overbought", "recovery", "pullback"))
    )
    if not correction_ok:
        result["view"] = "WAIT"
        result["reasons"] = ["intermediate screen does not show a correction aligned with the primary trend"]
        return result
    return with_direction(result, state, primary, "three screens align: primary trend, intermediate correction, and short trigger")
