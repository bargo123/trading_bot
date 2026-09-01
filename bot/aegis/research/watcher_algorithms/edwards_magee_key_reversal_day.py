"""Edwards--Magee Key Reversal Day short-term reversal study."""
from __future__ import annotations

from ._common import base, em_missing, explicitly_confirmed, first, normalized_status, values, with_direction

ALGORITHM_ID = "edwards_magee_key_reversal_day"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_key_reversal_trend",
    "em_key_reversal_extreme",
    "em_key_reversal_close_relation",
    "em_key_reversal_confirmation",
    "em_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "em_key_reversal_trend"))
    extreme = normalized_status(first(state, "em_key_reversal_extreme"))
    relation = normalized_status(first(state, "em_key_reversal_close_relation"))
    expected_extreme = "new high" if trend == "up" else "new low" if trend == "down" else None
    expected_relation = "below prior close" if trend == "up" else "above prior close" if trend == "down" else None
    if expected_extreme is None or extreme != expected_extreme or relation != expected_relation:
        result["edwards_magee_assessment"] = "KEY_REVERSAL_STRUCTURE_FAILED"
        result["reasons"] = ["the observed extreme and close must reverse the prior trend's previous-day close"]
        return result
    if not explicitly_confirmed(first(state, "em_key_reversal_confirmation")):
        result["edwards_magee_assessment"] = "KEY_REVERSAL_UNCONFIRMED"
        result["reasons"] = ["the key reversal day is not explicitly confirmed"]
        return result
    signal = "SELL" if trend == "up" else "BUY"
    result["edwards_magee_assessment"] = "KEY_REVERSAL_DAY"
    result["edwards_magee_horizon"] = "short_term"
    return with_direction(result, state, signal, "a new trend extreme failed to hold and the close reversed through the prior close")
