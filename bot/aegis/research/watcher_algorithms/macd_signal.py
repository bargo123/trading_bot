"""MACD relationship and histogram-cross perspective."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "macd_signal"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Alexander Elder — The New Trading for a Living",
    "Ernest Chan — Machine Trading",
)
KEYS = ("macd_line", "macd_signal", "macd_histogram", "macd_state", "macd_cross", "macd_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("macd_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, "macd_cross", "macd_state")
    if "cross_up" in text or "bullish" in text:
        return with_direction(result, state, "BUY", "MACD histogram/cross context is bullish at the copied timestamp")
    if "cross_down" in text or "bearish" in text:
        return with_direction(result, state, "SELL", "MACD histogram/cross context is bearish at the copied timestamp")
    result["view"] = "WAIT"
    result["reasons"] = ["MACD is observed without a directional histogram or cross confirmation"]
    return result
