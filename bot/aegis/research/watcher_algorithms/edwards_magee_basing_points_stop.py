"""Magee Basing Points procedure and non-loosening filtered stop study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, normalized_status, side, values

ALGORITHM_ID = "edwards_magee_basing_points_stop"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
BASE_KEYS = (
    "em_basing_mode",
    "em_day_away_count",
    "em_stop_filter_fraction",
    "em_existing_stop_price",
    "em_data_provenance",
)
KEYS = (
    *BASE_KEYS,
    "side",
    "em_basing_point_low",
    "em_basing_point_high",
    "em_lower_low_before_confirmation",
    "em_higher_high_before_confirmation",
    "em_new_wave_high",
    "em_previous_wave_high",
    "em_new_wave_low",
    "em_previous_wave_low",
    "em_new_extreme_threshold",
)


def _missing(state):
    missing = [key for key in BASE_KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "em_data_provenance"), accepted=("observed", "timestamped")):
        missing.append("em_data_provenance")
    candidate_side = side(state)
    mode = normalized_status(first(state, "em_basing_mode"))
    if candidate_side == "BUY" and mode == "wave low":
        required = ("em_basing_point_low", "em_lower_low_before_confirmation")
    elif candidate_side == "SELL" and mode == "wave low":
        required = ("em_basing_point_high", "em_higher_high_before_confirmation")
    elif candidate_side == "BUY" and mode == "new high":
        required = ("em_new_wave_high", "em_previous_wave_high", "em_basing_point_low", "em_new_extreme_threshold")
    elif candidate_side == "SELL" and mode == "new low":
        required = ("em_new_wave_low", "em_previous_wave_low", "em_basing_point_high", "em_new_extreme_threshold")
    else:
        required = ("side", "em_basing_mode")
    missing.extend(key for key in required if first(state, key) is None)
    return list(dict.fromkeys(missing))


def evaluate(state):
    found = values(state, *KEYS)
    missing = _missing(state)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    candidate_side = side(state)
    mode = normalized_status(first(state, "em_basing_mode"))
    away_count = number(first(state, "em_day_away_count"))
    filter_fraction = number(first(state, "em_stop_filter_fraction"))
    existing_stop = number(first(state, "em_existing_stop_price"))
    if (
        candidate_side not in {"BUY", "SELL"}
        or mode not in {"wave low", "new high", "new low"}
        or away_count is None
        or filter_fraction is None
        or not 0 < filter_fraction < 1
        or existing_stop is None
    ):
        result["edwards_magee_basing_assessment"] = "INVALID_BASING_INPUT"
        result["reasons"] = ["side, basing mode, away count, filter, and existing stop must be valid"]
        return result
    if mode == "wave low" and away_count < 3:
        result["edwards_magee_basing_assessment"] = "THREE_DAY_RULE_NOT_MET"
        result["reasons"] = ["a wave-low Basing Point requires three complete days away before a lower low"]
        return result

    if mode == "wave low":
        invalidated_key = "em_lower_low_before_confirmation" if candidate_side == "BUY" else "em_higher_high_before_confirmation"
        invalidated = first(state, invalidated_key)
        if not isinstance(invalidated, bool):
            result["edwards_magee_basing_assessment"] = "INVALID_BASING_INPUT"
            result["reasons"] = ["Basing Point invalidation must be an explicit boolean observation"]
            return result
        if invalidated:
            result["edwards_magee_basing_assessment"] = "BASING_POINT_INVALIDATED"
            result["reasons"] = ["the opposing extreme was made before the three-day-away confirmation"]
            return result
        anchor = number(first(state, "em_basing_point_low" if candidate_side == "BUY" else "em_basing_point_high"))
        if anchor is None or anchor <= 0:
            result["edwards_magee_basing_assessment"] = "INVALID_BASING_INPUT"
            result["reasons"] = ["the Basing Point anchor must be a positive finite price"]
            return result
        assessment = "BASING_POINT_CONFIRMED"
    else:
        threshold = number(first(state, "em_new_extreme_threshold"))
        current = number(first(state, "em_new_wave_high" if mode == "new high" else "em_new_wave_low"))
        previous = number(first(state, "em_previous_wave_high" if mode == "new high" else "em_previous_wave_low"))
        anchor = number(first(state, "em_basing_point_low" if candidate_side == "BUY" else "em_basing_point_high"))
        valid_threshold = threshold is not None and 0 < threshold < 1
        valid_prices = current is not None and previous is not None and anchor is not None and current > 0 and previous > 0 and anchor > 0
        if not valid_threshold or not valid_prices:
            result["edwards_magee_basing_assessment"] = "INVALID_BASING_INPUT"
            result["reasons"] = ["new-extreme Basing Points require valid prices and an explicit positive threshold"]
            return result
        extended = current >= previous * (1 + threshold) if mode == "new high" else current <= previous * (1 - threshold)
        if not extended:
            result["edwards_magee_basing_assessment"] = "NEW_EXTREME_RULE_NOT_MET"
            result["reasons"] = ["the new wave extreme has not exceeded the prior extreme by the observed threshold"]
            return result
        assessment = "NEW_EXTREME_BASING_POINT"

    candidate_stop = anchor * (1 - filter_fraction) if candidate_side == "BUY" else anchor * (1 + filter_fraction)
    loosens = candidate_stop <= existing_stop if candidate_side == "BUY" else candidate_stop >= existing_stop
    result["edwards_magee_candidate_stop"] = candidate_stop
    result["edwards_magee_existing_stop"] = existing_stop
    result["edwards_magee_stop_filter_fraction"] = filter_fraction
    result["edwards_magee_stop_ratchets"] = not loosens
    if loosens:
        result["edwards_magee_basing_assessment"] = "STOP_WOULD_LOOSEN"
        result["reasons"] = ["the proposed filtered stop is not tighter than the existing stop; stops never move backward"]
        return result
    result["edwards_magee_basing_assessment"] = assessment
    result["reasons"] = ["the observed Basing Point supports a filtered stop that only ratchets in the protective direction"]
    return result
