"""Ichimoku cloud relationship perspective from quote highs/lows."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "ichimoku_context"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Alexander Elder — The New Trading for a Living",
)
KEYS = ("tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b", "ichimoku_state", "ichimoku_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("ichimoku_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    cloud_state = strings(state, "ichimoku_state")
    if cloud_state == "bullish":
        return with_direction(result, state, "BUY", "price and conversion/base lines are above the observed cloud proxy")
    if cloud_state == "bearish":
        return with_direction(result, state, "SELL", "price and conversion/base lines are below the observed cloud proxy")
    result["view"] = "WAIT"
    result["reasons"] = ["price is within or conflicting with the observed cloud proxy"]
    return result
