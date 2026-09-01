"""Edwards-Magee trend-channel deterioration and break proxy."""
from __future__ import annotations

from ._common import base, em_missing, first, number, normalized_status, explicitly_confirmed, with_direction

ALGORITHM_ID = "edwards_magee_channel_deterioration"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = ("em_channel_direction", "em_channel_state", "em_channel_confirmation", "em_channel_break_margin_pips")


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    direction = normalized_status(first(state, "em_channel_direction"))
    channel_state = normalized_status(first(state, "em_channel_state"))
    if direction not in {"up", "down"} or channel_state not in {"basic line broken", "return line failure"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["no established channel deterioration is observed"]
        return result
    if channel_state == "return line failure":
        result["view"] = "WAIT"
        result["reasons"] = ["a missed return-line target warns of deterioration but is not a confirmed break"]
        return result
    margin = number(first(state, "em_channel_break_margin_pips"))
    if margin is None or margin < 1.0 or not explicitly_confirmed(first(state, "em_channel_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["channel-line penetration is not decisive"]
        return result
    return with_direction(result, state, "SELL" if direction == "up" else "BUY", "the established basic channel line was decisively penetrated")
