"""Numeric RSI extreme and divergence research perspective."""
from __future__ import annotations

from ._common import base, first, strings, values, with_direction

ALGORITHM_ID = "rsi_reversal"
SOURCES = (
    "Alexander Elder — The New Trading for a Living",
    "Marcel Link — High Probability Trading",
    "Ernest Chan — Algorithmic Trading and Quantitative Strategies",
)
KEYS = ("rsi", "rsi_state", "rsi_divergence", "momentum_divergence", "regime")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("rsi",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    rsi = first(state, "rsi")
    state_text = strings(state, "rsi_state", "rsi_divergence", "momentum_divergence")
    try:
        rsi_value = float(rsi)
    except (TypeError, ValueError):
        rsi_value = None
    if "oversold" in state_text or (rsi_value is not None and rsi_value <= 30.0):
        return with_direction(result, state, "BUY", "RSI is at or below the explicit oversold threshold")
    if "overbought" in state_text or (rsi_value is not None and rsi_value >= 70.0):
        return with_direction(result, state, "SELL", "RSI is at or above the explicit overbought threshold")
    result["view"] = "WAIT"
    result["reasons"] = ["RSI is observed without an extreme or confirmed divergence state"]
    return result
