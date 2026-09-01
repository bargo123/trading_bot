"""Oscillator extreme-state algorithm."""
from __future__ import annotations
from ._common import base, strings, values, with_direction

ALGORITHM_ID = "oscillator_signal"
SOURCES = ("Alexander Elder — The New Trading for a Living", "Marcel Link — High Probability Trading", "Steve Nison — Japanese Candlestick Charting Techniques")
KEYS = ("oscillator", "oscillator_state", "rsi", "stochastic", "stoch", "overbought", "oversold", "regime")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("oscillator_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if "overbought" in text:
        return with_direction(result, state, "SELL", "oscillator records overbought state")
    if "oversold" in text:
        return with_direction(result, state, "BUY", "oscillator records oversold state")
    result["view"] = "WAIT"
    result["reasons"] = ["oscillator is present without a defined extreme state"]
    return result
