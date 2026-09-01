"""DMI/ADX directional-strength perspective from quote observations."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "adx_trend_strength"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Robert Carver — Systematic Trading",
    "Marcel Link — High Probability Trading",
)
KEYS = ("adx", "di_plus", "di_minus", "adx_state", "adx_direction", "adx_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("adx_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = strings(state, "adx_state", "adx_direction")
    if "strong" not in state_text:
        result["view"] = "WAIT"
        result["reasons"] = ["directional strength is weak or not above the explicit ADX research threshold"]
        return result
    if "up" in state_text:
        return with_direction(result, state, "BUY", "quote-observation DMI direction is up with strong directional strength")
    if "down" in state_text:
        return with_direction(result, state, "SELL", "quote-observation DMI direction is down with strong directional strength")
    result["view"] = "WAIT"
    result["reasons"] = ["strong directional strength has no resolved DMI direction"]
    return result
