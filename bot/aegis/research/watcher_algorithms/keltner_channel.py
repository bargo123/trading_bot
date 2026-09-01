"""Keltner-style volatility channel perspective."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "keltner_channel"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "John F. Carter — Mastering the Trade",
    "Robert Carver — Systematic Trading",
)
KEYS = ("keltner_middle", "keltner_upper", "keltner_lower", "keltner_width", "keltner_state", "keltner_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("keltner_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    channel_state = strings(state, "keltner_state")
    if "above_upper" in channel_state:
        return with_direction(result, state, "BUY", "price is above the observed upper Keltner proxy")
    if "below_lower" in channel_state:
        return with_direction(result, state, "SELL", "price is below the observed lower Keltner proxy")
    result["view"] = "WAIT"
    result["reasons"] = ["price remains inside the observed Keltner proxy channel"]
    return result
