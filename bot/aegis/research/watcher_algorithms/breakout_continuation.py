"""Read-only confirmed breakout-continuation perspective."""
from __future__ import annotations

from ._common import base, explicitly_confirmed, first, normalized_status, values, with_direction

ALGORITHM_ID = "breakout_continuation"
SOURCES = (
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Bob Volman — Forex Price Action Scalping",
    "Alexander Elder — The New Trading for a Living",
)
KEYS = ("breakout_state", "breakout_confirmation", "break_direction", "retest", "follow_through")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("confirmed_breakout",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    breakout = normalized_status(first(state, "breakout_state"))
    confirmation = normalized_status(first(state, "breakout_confirmation"))
    direction = normalized_status(first(state, "break_direction"))
    retest = normalized_status(first(state, "retest"))
    if "failed" in breakout or "failed" in confirmation:
        result["view"] = "WAIT"
        result["reasons"] = ["breakout failure is incompatible with continuation"]
        return result
    if breakout == "breakout up confirmed" or (direction == "up" and (explicitly_confirmed(confirmation) or explicitly_confirmed(retest))):
        return with_direction(result, state, "BUY", "confirmed upside breakout supports continuation")
    if breakout == "breakout down confirmed" or (direction == "down" and (explicitly_confirmed(confirmation) or explicitly_confirmed(retest))):
        return with_direction(result, state, "SELL", "confirmed downside breakout supports continuation")
    result["view"] = "WAIT"
    result["reasons"] = ["no confirmed directional breakout is observed"]
    return result
