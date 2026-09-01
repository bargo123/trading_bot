"""Bulkowski broadening-bottom megaphone and confirmed-breakout perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_broadening_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "11-15"
KEYS = (
    "bulkowski_broadening_type", "bulkowski_broadening_prior_trend",
    "bulkowski_broadening_top_slope", "bulkowski_broadening_bottom_slope",
    "bulkowski_broadening_top_touches", "bulkowski_broadening_bottom_touches",
    "bulkowski_broadening_breakout_direction", "bulkowski_broadening_breakout_close_confirmed",
    "bulkowski_broadening_breakout_price", "bulkowski_broadening_high",
    "bulkowski_broadening_low", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_broadening_type")) != "bottom":
        result["reasons"] = ["this perspective requires a broadening bottom"]
        return result
    if normalized_status(first(state, "bulkowski_broadening_prior_trend")) != "down":
        result["reasons"] = ["a broadening bottom requires a declining trend into the formation"]
        return result
    top_slope = number(first(state, "bulkowski_broadening_top_slope"))
    bottom_slope = number(first(state, "bulkowski_broadening_bottom_slope"))
    top_touches = number(first(state, "bulkowski_broadening_top_touches"))
    bottom_touches = number(first(state, "bulkowski_broadening_bottom_touches"))
    breakout_price = number(first(state, "bulkowski_broadening_breakout_price"))
    high = number(first(state, "bulkowski_broadening_high"))
    low = number(first(state, "bulkowski_broadening_low"))
    breakout = direction(state, "bulkowski_broadening_breakout_direction")
    if None in (top_slope, bottom_slope, top_touches, bottom_touches, breakout_price, high, low) or breakout is None:
        result["reasons"] = ["broadening slopes, touches, breakout, and range must be finite observations"]
        return result
    if top_slope <= 0 or bottom_slope >= 0 or top_touches < 2 or bottom_touches < 2 or high <= low:
        result["reasons"] = ["a broadening bottom needs diverging positive/negative boundaries and two touches on each side"]
        return result
    if not observed_bool(first(state, "bulkowski_broadening_breakout_close_confirmed")):
        result["reasons"] = ["the broadening-bottom breakout is not confirmed by a close outside the formation"]
        return result
    if (breakout == "UP" and breakout_price <= high) or (breakout == "DOWN" and breakout_price >= low):
        result["reasons"] = ["the confirmed close is not outside the broadening-bottom range"]
        return result
    height = high - low
    result.update({
        "source_pages": SOURCE_PAGES,
        "bulkowski_measure_target": breakout_price + height if breakout == "UP" else breakout_price - height,
        "bulkowski_formation_height": height,
    })
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a declining-trend megaphone has diverging boundaries and a confirmed range breakout")
