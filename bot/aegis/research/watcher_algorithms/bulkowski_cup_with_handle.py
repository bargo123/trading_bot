"""Bulkowski cup-with-handle continuation perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_cup_with_handle"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "149-153"
KEYS = (
    "bulkowski_cup_type", "bulkowski_cup_prior_trend", "bulkowski_cup_prior_rise_pct",
    "bulkowski_cup_shape", "bulkowski_cup_duration_weeks", "bulkowski_cup_handle_duration_days",
    "bulkowski_cup_handle_trend", "bulkowski_cup_handle_retrace_pct", "bulkowski_cup_handle_upper_half",
    "bulkowski_cup_left_lip", "bulkowski_cup_right_lip", "bulkowski_cup_low", "bulkowski_cup_high",
    "bulkowski_cup_breakout_direction", "bulkowski_cup_breakout_close_confirmed",
    "bulkowski_cup_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_cup_type")) != "normal":
        result["reasons"] = ["this perspective requires a normal cup with handle"]
        return result
    prior_rise = number(first(state, "bulkowski_cup_prior_rise_pct"))
    duration = number(first(state, "bulkowski_cup_duration_weeks"))
    handle_duration = number(first(state, "bulkowski_cup_handle_duration_days"))
    retrace = number(first(state, "bulkowski_cup_handle_retrace_pct"))
    left = number(first(state, "bulkowski_cup_left_lip"))
    right = number(first(state, "bulkowski_cup_right_lip"))
    low = number(first(state, "bulkowski_cup_low"))
    breakout_price = number(first(state, "bulkowski_cup_breakout_price"))
    breakout = direction(state, "bulkowski_cup_breakout_direction")
    if None in (prior_rise, duration, handle_duration, retrace, left, right, low, breakout_price) or breakout is None:
        result["reasons"] = ["cup rise, duration, handle, lips, breakout, and low must be finite observations"]
        return result
    if normalized_status(first(state, "bulkowski_cup_prior_trend")) != "up" or prior_rise < 30 or normalized_status(first(state, "bulkowski_cup_shape")) not in {"rounded", "u shaped", "u shape"}:
        result["reasons"] = ["a valid cup requires an upward prior rise of at least 30% and a rounded U-shaped cup"]
        return result
    if not 7 <= duration <= 65 or handle_duration < 5 or normalized_status(first(state, "bulkowski_cup_handle_trend")) != "down" or retrace <= 0 or not observed_bool(first(state, "bulkowski_cup_handle_upper_half")):
        result["reasons"] = ["the cup duration, downward handle, retrace, and upper-half handle tests failed"]
        return result
    if left <= 0 or right <= 0 or low >= min(left, right) or abs(left - right) / min(left, right) > 0.06:
        result["reasons"] = ["cup lips must be near the same level above a finite rounded-cup low"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_cup_breakout_close_confirmed")) or breakout_price <= max(left, right):
        result["reasons"] = ["the cup requires a confirmed close above both cup lips"]
        return result
    height = min(left, right) - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": breakout_price + height, "bulkowski_cup_height": height, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "a rounded cup after a substantial rise formed an upper-half handle and confirmed above the lips")
