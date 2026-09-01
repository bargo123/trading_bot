"""Bulkowski descending triangle: falling resistance over flat support."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_descending_triangle"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "730-738"
KEYS = (
    "bulkowski_desc_triangle_top_slope", "bulkowski_desc_triangle_bottom_slope",
    "bulkowski_desc_triangle_top_touches", "bulkowski_desc_triangle_bottom_touches",
    "bulkowski_desc_triangle_horizontal_support_confirmed", "bulkowski_desc_triangle_white_space_covered",
    "bulkowski_desc_triangle_high", "bulkowski_desc_triangle_low",
    "bulkowski_desc_triangle_breakout_direction", "bulkowski_desc_triangle_breakout_close_confirmed",
    "bulkowski_desc_triangle_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    top_slope = number(first(state, "bulkowski_desc_triangle_top_slope"))
    bottom_slope = number(first(state, "bulkowski_desc_triangle_bottom_slope"))
    top_touches = number(first(state, "bulkowski_desc_triangle_top_touches"))
    bottom_touches = number(first(state, "bulkowski_desc_triangle_bottom_touches"))
    high = number(first(state, "bulkowski_desc_triangle_high"))
    low = number(first(state, "bulkowski_desc_triangle_low"))
    price = number(first(state, "bulkowski_desc_triangle_breakout_price"))
    breakout = direction(state, "bulkowski_desc_triangle_breakout_direction")
    if None in (top_slope, bottom_slope, top_touches, bottom_touches, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["descending-triangle boundaries, touches, and breakout must be finite and ordered"]
        return result
    if top_slope >= 0 or abs(bottom_slope) > 0.10:
        result["reasons"] = ["a descending triangle needs a down-sloping top and nearly horizontal support"]
        return result
    if top_touches < 2 or bottom_touches < 2 or not observed_bool(first(state, "bulkowski_desc_triangle_horizontal_support_confirmed")) or not observed_bool(first(state, "bulkowski_desc_triangle_white_space_covered")):
        result["reasons"] = ["the triangle needs distinct touches on both boundaries and crossed white space"]
        return result
    if not observed_bool(first(state, "bulkowski_desc_triangle_breakout_close_confirmed")) or ((breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low)):
        result["reasons"] = ["the descending-triangle breakout is not a confirmed close outside the boundaries"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_triangle_height": height, "bulkowski_measure_target": price + height if breakout == "UP" else price - height, "bulkowski_stop_price": low if breakout == "UP" else high})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a down-sloping resistance line and flat support formed a confirmed descending triangle break")
