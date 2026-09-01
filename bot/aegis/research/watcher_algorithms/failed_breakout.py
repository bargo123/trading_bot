"""Read-only failed-breakout reversal perspective."""
from __future__ import annotations

from ._common import base, first, normalized_status, values, with_direction

ALGORITHM_ID = "failed_breakout"
SOURCES = (
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Thomas Bulkowski — Encyclopedia of Chart Patterns",
    "Anna Coulling — A Complete Guide to Volume Price Analysis",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = ("breakout_state", "breakout_confirmation", "break_direction", "structure")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("breakout_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    breakout = normalized_status(first(state, "breakout_state"))
    confirmation = normalized_status(first(state, "breakout_confirmation"))
    direction = normalized_status(first(state, "break_direction"))
    if breakout == "failed break up" or (confirmation == "failed quote break" and direction == "up"):
        return with_direction(result, state, "SELL", "upside breakout failure was observed")
    if breakout == "failed break down" or (confirmation == "failed quote break" and direction == "down"):
        return with_direction(result, state, "BUY", "downside breakout failure was observed")
    result["view"] = "WAIT"
    result["reasons"] = ["no failed breakout trigger is observed"]
    return result

