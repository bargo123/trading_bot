"""Bulkowski rectangle top: horizontal range after a rising trend."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_rectangle_top"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "579-586"
KEYS = (
    "bulkowski_rectangle_type", "bulkowski_rectangle_prior_trend",
    "bulkowski_rectangle_upper_slope", "bulkowski_rectangle_lower_slope",
    "bulkowski_rectangle_horizontal_boundaries_confirmed", "bulkowski_rectangle_upper_touches",
    "bulkowski_rectangle_lower_touches", "bulkowski_rectangle_high", "bulkowski_rectangle_low",
    "bulkowski_rectangle_breakout_direction", "bulkowski_rectangle_breakout_close_confirmed",
    "bulkowski_rectangle_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    upper_slope = number(first(state, "bulkowski_rectangle_upper_slope"))
    lower_slope = number(first(state, "bulkowski_rectangle_lower_slope"))
    upper_touches = number(first(state, "bulkowski_rectangle_upper_touches"))
    lower_touches = number(first(state, "bulkowski_rectangle_lower_touches"))
    high = number(first(state, "bulkowski_rectangle_high"))
    low = number(first(state, "bulkowski_rectangle_low"))
    price = number(first(state, "bulkowski_rectangle_breakout_price"))
    breakout = direction(state, "bulkowski_rectangle_breakout_direction")
    if normalized_status(first(state, "bulkowski_rectangle_type")) != "top" or normalized_status(first(state, "bulkowski_rectangle_prior_trend")) != "up":
        result["reasons"] = ["a rectangle top requires a prevailing rising trend"]
        return result
    if None in (upper_slope, lower_slope, upper_touches, lower_touches, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["rectangle boundaries, touches, and breakout must be finite and ordered"]
        return result
    if not observed_bool(first(state, "bulkowski_rectangle_horizontal_boundaries_confirmed")) or abs(upper_slope) > 0.10 or abs(lower_slope) > 0.10:
        result["reasons"] = ["rectangle boundaries must be observed as horizontal or nearly horizontal"]
        return result
    if upper_touches < 2 or lower_touches < 2:
        result["reasons"] = ["a rectangle needs at least two distinct touches on each boundary"]
        return result
    if not observed_bool(first(state, "bulkowski_rectangle_breakout_close_confirmed")) or ((breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low)):
        result["reasons"] = ["the rectangle breakout is not a confirmed close outside the range"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_rectangle_height": height, "bulkowski_measure_target": price + height if breakout == "UP" else price - height, "bulkowski_stop_price": low if breakout == "UP" else high})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a rising-trend rectangle supplied two-sided horizontal support and resistance")
