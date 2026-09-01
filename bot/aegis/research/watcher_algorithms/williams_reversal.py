"""Williams %R extreme perspective."""
from __future__ import annotations

from ._common import base, first, strings, values, with_direction

ALGORITHM_ID = "williams_reversal"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Marcel Link — High Probability Trading",
)
KEYS = ("williams_r", "williams_state", "williams_observation_n", "regime")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("williams_r",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = strings(state, "williams_state")
    try:
        value = float(first(state, "williams_r"))
    except (TypeError, ValueError):
        value = None
    if "oversold" in state_text or (value is not None and value <= -80.0):
        return with_direction(result, state, "BUY", "Williams %R is at or below the explicit oversold threshold")
    if "overbought" in state_text or (value is not None and value >= -20.0):
        return with_direction(result, state, "SELL", "Williams %R is at or above the explicit overbought threshold")
    result["view"] = "WAIT"
    result["reasons"] = ["Williams %R is observed without an explicit extreme state"]
    return result
