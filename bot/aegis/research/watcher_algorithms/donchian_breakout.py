"""Donchian-style observed-range breakout perspective."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "donchian_breakout"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Robert Carver — Systematic Trading",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = ("donchian_high", "donchian_low", "donchian_width", "donchian_state", "breakout_state", "breakout_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("observed_donchian_range",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, "donchian_state", "breakout_state", "breakout_confirmation")
    if "failed" in text or "false" in text or "unconfirmed" in text:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed channel break has failed or is explicitly unconfirmed"]
        return result
    if "breakout_up" in text:
        return with_direction(result, state, "BUY", "observed upper channel breakout is recorded")
    if "breakout_down" in text:
        return with_direction(result, state, "SELL", "observed lower channel breakout is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["price remains inside the observed Donchian range"]
    return result
