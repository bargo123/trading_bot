"""Bollinger-inside-Keltner squeeze release with momentum confirmation."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, number, strings, values, with_direction

ALGORITHM_ID = "ttm_squeeze"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = ("squeeze_state", "squeeze_direction", "squeeze_momentum", "squeeze_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("squeeze_release_and_momentum",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = strings(state, "squeeze_state")
    direction_text = strings(state, "squeeze_direction")
    momentum = number(first(state, "squeeze_momentum"))
    if "release" not in state_text or not explicitly_confirmed(first(state, "squeeze_confirmation")) or momentum is None:
        result["view"] = "WAIT"
        result["reasons"] = ["squeeze must release with a confirmed directional momentum reading"]
        return result
    if momentum > 0 and "up" in direction_text:
        return with_direction(result, state, "BUY", "released squeeze has positive confirmed momentum")
    if momentum < 0 and "down" in direction_text:
        return with_direction(result, state, "SELL", "released squeeze has negative confirmed momentum")
    result["view"] = "WAIT"
    result["reasons"] = ["squeeze direction and momentum do not agree"]
    return result
