"""Bulkowski symmetrical triangle: converging falling highs and rising lows."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_symmetrical_triangle"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "748-754"
KEYS = (
    "bulkowski_sym_triangle_upper_slope", "bulkowski_sym_triangle_lower_slope",
    "bulkowski_sym_triangle_upper_touches", "bulkowski_sym_triangle_lower_touches",
    "bulkowski_sym_triangle_converging_confirmed", "bulkowski_sym_triangle_white_space_covered",
    "bulkowski_sym_triangle_duration_weeks", "bulkowski_sym_triangle_high",
    "bulkowski_sym_triangle_low", "bulkowski_sym_triangle_breakout_direction",
    "bulkowski_sym_triangle_breakout_close_confirmed", "bulkowski_sym_triangle_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    upper_slope = number(first(state, "bulkowski_sym_triangle_upper_slope"))
    lower_slope = number(first(state, "bulkowski_sym_triangle_lower_slope"))
    upper_touches = number(first(state, "bulkowski_sym_triangle_upper_touches"))
    lower_touches = number(first(state, "bulkowski_sym_triangle_lower_touches"))
    duration = number(first(state, "bulkowski_sym_triangle_duration_weeks"))
    high = number(first(state, "bulkowski_sym_triangle_high"))
    low = number(first(state, "bulkowski_sym_triangle_low"))
    price = number(first(state, "bulkowski_sym_triangle_breakout_price"))
    breakout = direction(state, "bulkowski_sym_triangle_breakout_direction")
    if None in (upper_slope, lower_slope, upper_touches, lower_touches, duration, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["symmetrical-triangle boundaries, duration, and breakout must be finite observations"]
        return result
    if upper_slope >= 0 or lower_slope <= 0 or duration <= 3:
        result["reasons"] = ["a symmetrical triangle needs falling highs, rising lows, and more than three weeks"]
        return result
    if upper_touches < 2 or lower_touches < 2 or not observed_bool(first(state, "bulkowski_sym_triangle_converging_confirmed")) or not observed_bool(first(state, "bulkowski_sym_triangle_white_space_covered")):
        result["reasons"] = ["the triangle needs converging boundaries, two touches on each side, and crossed white space"]
        return result
    if not observed_bool(first(state, "bulkowski_sym_triangle_breakout_close_confirmed")) or ((breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low)):
        result["reasons"] = ["the symmetrical-triangle breakout is not a confirmed close outside the boundaries"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_triangle_height": height, "bulkowski_measure_target": price + height if breakout == "UP" else price - height, "bulkowski_stop_price": low if breakout == "UP" else high})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "falling highs and rising lows converged into a confirmed symmetrical-triangle break")
