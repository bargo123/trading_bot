"""Bulkowski rising wedge: two rising boundaries narrowing toward the apex."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_rising_wedge"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "811-821"
KEYS = (
    "bulkowski_rising_wedge_upper_slope", "bulkowski_rising_wedge_lower_slope",
    "bulkowski_rising_wedge_upper_touches", "bulkowski_rising_wedge_lower_touches",
    "bulkowski_rising_wedge_duration_weeks", "bulkowski_rising_wedge_breakout_direction",
    "bulkowski_rising_wedge_breakout_close_confirmed", "bulkowski_rising_wedge_breakout_price",
    "bulkowski_rising_wedge_high", "bulkowski_rising_wedge_low", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    upper_slope = number(first(state, "bulkowski_rising_wedge_upper_slope"))
    lower_slope = number(first(state, "bulkowski_rising_wedge_lower_slope"))
    upper_touches = number(first(state, "bulkowski_rising_wedge_upper_touches"))
    lower_touches = number(first(state, "bulkowski_rising_wedge_lower_touches"))
    duration = number(first(state, "bulkowski_rising_wedge_duration_weeks"))
    high = number(first(state, "bulkowski_rising_wedge_high"))
    low = number(first(state, "bulkowski_rising_wedge_low"))
    price = number(first(state, "bulkowski_rising_wedge_breakout_price"))
    breakout = direction(state, "bulkowski_rising_wedge_breakout_direction")
    if None in (upper_slope, lower_slope, upper_touches, lower_touches, duration, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["rising-wedge slopes, touches, duration, and breakout must be finite observations"]
        return result
    if upper_slope <= 0 or lower_slope <= upper_slope or duration < 3:
        result["reasons"] = ["a rising wedge needs two upward slopes, a faster lower boundary, and at least three weeks"]
        return result
    if upper_touches < 2 or lower_touches < 3 or upper_touches + lower_touches < 5:
        result["reasons"] = ["a rising wedge needs at least five distinct touches across its boundaries"]
        return result
    if not observed_bool(first(state, "bulkowski_rising_wedge_breakout_close_confirmed")) or ((breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low)):
        result["reasons"] = ["the rising-wedge breakout is not a confirmed close outside the boundaries"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_wedge_height": height, "bulkowski_measure_target": price + height if breakout == "UP" else price - height, "bulkowski_stop_price": low if breakout == "UP" else high})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "two narrowing upward trend lines and five touches formed a confirmed rising-wedge break")
