"""Bulkowski inverted cup-with-handle bearish breakout perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_inverted_cup_with_handle"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "164-168"
KEYS = (
    "bulkowski_cup_type", "bulkowski_cup_prior_trend", "bulkowski_cup_shape",
    "bulkowski_cup_duration_weeks", "bulkowski_cup_handle_duration_days", "bulkowski_cup_handle_retrace_pct",
    "bulkowski_cup_handle_exceeds_top", "bulkowski_cup_left_lip", "bulkowski_cup_right_lip",
    "bulkowski_cup_low", "bulkowski_cup_high", "bulkowski_cup_handle_height",
    "bulkowski_cup_breakout_direction", "bulkowski_cup_breakout_close_confirmed",
    "bulkowski_cup_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_cup_type")) != "inverted":
        result["reasons"] = ["this perspective requires an inverted cup with handle"]
        return result
    duration = number(first(state, "bulkowski_cup_duration_weeks"))
    handle_duration = number(first(state, "bulkowski_cup_handle_duration_days"))
    retrace = number(first(state, "bulkowski_cup_handle_retrace_pct"))
    left = number(first(state, "bulkowski_cup_left_lip"))
    right = number(first(state, "bulkowski_cup_right_lip"))
    low = number(first(state, "bulkowski_cup_low"))
    high = number(first(state, "bulkowski_cup_high"))
    handle_height = number(first(state, "bulkowski_cup_handle_height"))
    breakout_price = number(first(state, "bulkowski_cup_breakout_price"))
    breakout = direction(state, "bulkowski_cup_breakout_direction")
    if None in (duration, handle_duration, retrace, left, right, low, high, handle_height, breakout_price) or breakout is None:
        result["reasons"] = ["inverted-cup duration, handle, lips, range, and breakout must be finite observations"]
        return result
    if normalized_status(first(state, "bulkowski_cup_prior_trend")) not in {"up", "down"} or normalized_status(first(state, "bulkowski_cup_shape")) not in {"rounded", "u shaped", "u shape"}:
        result["reasons"] = ["the inverted cup requires a rounded observed cup and a known prior trend"]
        return result
    if duration < 7 or duration > 65 or handle_duration < 1 or retrace <= 0 or observed_bool(first(state, "bulkowski_cup_handle_exceeds_top")):
        result["reasons"] = ["the inverted-cup duration, handle retrace, or handle-top constraint failed"]
        return result
    if left <= 0 or right <= 0 or high <= max(left, right) or low >= min(left, right) or abs(left - right) / min(left, right) > 0.06:
        result["reasons"] = ["inverted-cup rims must be near the same level within a finite range"]
        return result
    if breakout != "DOWN" or not observed_bool(first(state, "bulkowski_cup_breakout_close_confirmed")) or breakout_price >= right:
        result["reasons"] = ["the inverted cup requires a confirmed close below the right cup rim"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": breakout_price - handle_height, "bulkowski_handle_height": handle_height, "bulkowski_stop_price": high})
    return finish(result, state, "SELL", "a rounded inverted cup formed a bounded handle and confirmed below the right rim")
