"""Numeric stochastic extreme and reversal perspective."""
from __future__ import annotations

from ._common import base, first, strings, values, with_direction

ALGORITHM_ID = "stochastic_reversal"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Alexander Elder — The New Trading for a Living",
    "Marcel Link — High Probability Trading",
)
KEYS = ("stochastic_k", "stochastic", "stoch", "stochastic_state", "regime", "trend")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("stochastic",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = strings(state, "stochastic_state")
    raw = first(state, "stochastic_k", "stochastic", "stoch")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = None
    if "oversold" in state_text or (value is not None and value <= 20.0):
        return with_direction(result, state, "BUY", "stochastic is at or below the explicit oversold threshold")
    if "overbought" in state_text or (value is not None and value >= 80.0):
        return with_direction(result, state, "SELL", "stochastic is at or above the explicit overbought threshold")
    result["view"] = "WAIT"
    result["reasons"] = ["stochastic is observed without an explicit extreme state"]
    return result
