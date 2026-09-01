"""Nison disparity-index extreme with confirmed reversal context."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_disparity_reversal"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_disparity_state",
    "nison_reversal_direction",
    "nison_reversal_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_reversal_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["disparity extreme is context until a reversal is confirmed"]
        return result
    extreme = normalized_status(first(state, "nison_disparity_state"))
    direction = normalized_status(first(state, "nison_reversal_direction"))
    if extreme == "oversold" and direction == "up":
        return with_direction(result, state, "BUY", "oversold disparity aligned with a confirmed upside reversal")
    if extreme == "overbought" and direction == "down":
        return with_direction(result, state, "SELL", "overbought disparity aligned with a confirmed downside reversal")
    result["view"] = "WAIT"
    result["reasons"] = ["disparity extreme and reversal direction do not agree"]
    return result
