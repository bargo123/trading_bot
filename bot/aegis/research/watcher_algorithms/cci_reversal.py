"""Commodity Channel Index extreme perspective."""
from __future__ import annotations

from ._common import base, first, strings, values, with_direction

ALGORITHM_ID = "cci_reversal"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Marcel Link — High Probability Trading",
)
KEYS = ("cci", "cci_state", "cci_observation_n", "regime")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("cci",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = strings(state, "cci_state")
    try:
        value = float(first(state, "cci"))
    except (TypeError, ValueError):
        value = None
    if "oversold" in state_text or (value is not None and value <= -100.0):
        return with_direction(result, state, "BUY", "CCI is at or below the explicit oversold threshold")
    if "overbought" in state_text or (value is not None and value >= 100.0):
        return with_direction(result, state, "SELL", "CCI is at or above the explicit overbought threshold")
    result["view"] = "WAIT"
    result["reasons"] = ["CCI is observed without an explicit extreme state"]
    return result
