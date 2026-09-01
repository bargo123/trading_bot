"""Bulkowski descending broadening-wedge structure and breakout perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_descending_broadening_wedge"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "98-103"
KEYS = (
    "bulkowski_broadening_wedge_type", "bulkowski_broadening_wedge_upper_slope",
    "bulkowski_broadening_wedge_lower_slope", "bulkowski_broadening_wedge_upper_touches",
    "bulkowski_broadening_wedge_lower_touches", "bulkowski_broadening_wedge_breakout_direction",
    "bulkowski_broadening_wedge_breakout_close_confirmed", "bulkowski_broadening_wedge_breakout_price",
    "bulkowski_broadening_wedge_high", "bulkowski_broadening_wedge_low", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_broadening_wedge_type")) != "descending":
        result["reasons"] = ["this perspective requires a descending broadening wedge"]
        return result
    upper = number(first(state, "bulkowski_broadening_wedge_upper_slope"))
    lower = number(first(state, "bulkowski_broadening_wedge_lower_slope"))
    upper_touches = number(first(state, "bulkowski_broadening_wedge_upper_touches"))
    lower_touches = number(first(state, "bulkowski_broadening_wedge_lower_touches"))
    breakout_price = number(first(state, "bulkowski_broadening_wedge_breakout_price"))
    high = number(first(state, "bulkowski_broadening_wedge_high"))
    low = number(first(state, "bulkowski_broadening_wedge_low"))
    breakout = direction(state, "bulkowski_broadening_wedge_breakout_direction")
    if None in (upper, lower, upper_touches, lower_touches, breakout_price, high, low) or breakout is None:
        result["reasons"] = ["wedge slopes, touches, breakout, and range must be finite observations"]
        return result
    if not (0 > upper > lower) or upper_touches < 2 or lower_touches < 2 or high <= low:
        result["reasons"] = ["a descending broadening wedge needs two falling, diverging boundaries and two touches on each side"]
        return result
    if not observed_bool(first(state, "bulkowski_broadening_wedge_breakout_close_confirmed")):
        result["reasons"] = ["the descending broadening-wedge breakout is not confirmed"]
        return result
    if (breakout == "UP" and breakout_price <= high) or (breakout == "DOWN" and breakout_price >= low):
        result["reasons"] = ["the confirmed close is not outside the descending broadening-wedge range"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": breakout_price + height if breakout == "UP" else breakout_price - height, "bulkowski_formation_height": height})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "two falling, diverging boundaries and a confirmed breakout identify the descending broadening wedge")
