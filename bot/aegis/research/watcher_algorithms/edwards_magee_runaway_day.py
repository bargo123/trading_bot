"""Edwards--Magee runaway-day continuation or false-signal study."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "edwards_magee_runaway_day"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_runaway_direction",
    "em_runaway_range_ratio",
    "em_runaway_close_location",
    "em_runaway_followup",
    "em_runaway_returned_to_origin",
    "em_runaway_confirmation",
    "em_data_provenance",
    "em_volume_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    move = normalized_status(first(state, "em_runaway_direction"))
    close_location = normalized_status(first(state, "em_runaway_close_location"))
    range_ratio = number(first(state, "em_runaway_range_ratio"))
    followup = normalized_status(first(state, "em_runaway_followup"))
    returned = first(state, "em_runaway_returned_to_origin")
    if move not in {"up", "down"} or close_location not in {"near high", "near low"} or range_ratio is None or range_ratio < 2.0 or not isinstance(returned, bool):
        result["edwards_magee_assessment"] = "INVALID_RUNAWAY_INPUT"
        result["reasons"] = ["runaway direction, wide range, close location, and origin-return observation must be valid"]
        return result
    expected_location = "near high" if move == "up" else "near low"
    if close_location != expected_location:
        result["edwards_magee_assessment"] = "RUNAWAY_CLOSE_NOT_DIRECTIONAL"
        result["reasons"] = ["the wide-range close does not support the declared runaway direction"]
        return result
    if not em_real_volume(state):
        result["edwards_magee_assessment"] = "SOURCE_VOLUME_UNAVAILABLE"
        result["warnings"] = ["runaway validation requires continued real volume; tick activity is not interchangeable"]
        return result
    if followup == "continued volume":
        if returned:
            result["edwards_magee_assessment"] = "RUNAWAY_FOLLOWUP_CONTRADICTED"
            result["reasons"] = ["a return to the origin invalidates the continuation interpretation"]
            return result
        if not explicitly_confirmed(first(state, "em_runaway_confirmation")):
            result["edwards_magee_assessment"] = "RUNAWAY_UNCONFIRMED"
            result["reasons"] = ["continued volume and consolidation are not explicitly confirmed"]
            return result
        signal = "BUY" if move == "up" else "SELL"
        result["edwards_magee_assessment"] = "RUNAWAY_CONTINUATION"
        return with_direction(result, state, signal, "the wide-range directional day held with continued real volume")
    if followup == "false return" and returned:
        if not explicitly_confirmed(first(state, "em_runaway_confirmation")):
            result["edwards_magee_assessment"] = "RUNAWAY_FALSE_SIGNAL_UNCONFIRMED"
            result["reasons"] = ["the return to the origin is not explicitly confirmed"]
            return result
        signal = "SELL" if move == "up" else "BUY"
        result["edwards_magee_assessment"] = "RUNAWAY_FALSE_SIGNAL"
        return with_direction(result, state, signal, "the directional day returned to its origin, marking a false signal and reversal risk")
    result["edwards_magee_assessment"] = "RUNAWAY_FOLLOWUP_UNRESOLVED"
    result["reasons"] = ["runaway follow-up and return-to-origin observations are inconsistent"]
    return result
