"""Edwards-Magee gap classification and confirmation proxy."""
from __future__ import annotations

from ._common import base, em_missing, first, number, normalized_status, explicitly_confirmed, with_direction

ALGORITHM_ID = "edwards_magee_gap_classification"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = ("em_gap_type", "em_gap_direction", "em_gap_confirmation", "em_gap_size_pips")


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    gap_type = normalized_status(first(state, "em_gap_type"))
    if gap_type not in {"area", "breakaway", "runaway", "exhaustion"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["no classified gap event is observed"]
        return result
    size = number(first(state, "em_gap_size_pips"))
    if size is None or size < 1.0 or not explicitly_confirmed(first(state, "em_gap_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["gap size or confirmation is insufficient"]
        return result
    direction = normalized_status(first(state, "em_gap_direction"))
    if direction not in {"up", "down"}:
        result["view"] = "WAIT"
        result["reasons"] = ["gap direction is unresolved"]
        return result
    if gap_type == "area":
        result["view"] = "WAIT"
        result["reasons"] = ["area gaps have little forecasting significance and usually belong to congestion"]
        return result
    signal = "SELL" if direction == "down" else "BUY"
    if gap_type == "exhaustion":
        signal = "BUY" if direction == "down" else "SELL"
        reason = "confirmed exhaustion gap favors the reversal direction"
    else:
        reason = "confirmed breakaway or continuation gap supports the gap direction"
    return with_direction(result, state, signal, reason)
