"""Bulkowski right-angled ascending broadening formation perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_right_angled_ascending"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "28-32"
KEYS = (
    "bulkowski_right_angled_type", "bulkowski_right_angled_prior_trend",
    "bulkowski_right_angled_horizontal_slope", "bulkowski_right_angled_sloped_slope",
    "bulkowski_right_angled_horizontal_touches", "bulkowski_right_angled_sloped_touches",
    "bulkowski_right_angled_breakout_direction", "bulkowski_right_angled_breakout_close_confirmed",
    "bulkowski_right_angled_breakout_price", "bulkowski_right_angled_high",
    "bulkowski_right_angled_low", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_right_angled_type")) != "ascending":
        result["reasons"] = ["this perspective requires a right-angled ascending formation"]
        return result
    horizontal = number(first(state, "bulkowski_right_angled_horizontal_slope"))
    sloped = number(first(state, "bulkowski_right_angled_sloped_slope"))
    horizontal_touches = number(first(state, "bulkowski_right_angled_horizontal_touches"))
    sloped_touches = number(first(state, "bulkowski_right_angled_sloped_touches"))
    breakout_price = number(first(state, "bulkowski_right_angled_breakout_price"))
    high = number(first(state, "bulkowski_right_angled_high"))
    low = number(first(state, "bulkowski_right_angled_low"))
    breakout = direction(state, "bulkowski_right_angled_breakout_direction")
    if None in (horizontal, sloped, horizontal_touches, sloped_touches, breakout_price, high, low) or breakout is None:
        result["reasons"] = ["right-angled boundaries, touches, breakout, and range must be finite observations"]
        return result
    if abs(horizontal) > 0.02 or sloped <= 0 or horizontal_touches < 2 or sloped_touches < 2 or high <= low:
        result["reasons"] = ["the ascending right-angled formation needs a horizontal base and rising upper boundary with two touches each"]
        return result
    if not observed_bool(first(state, "bulkowski_right_angled_breakout_close_confirmed")):
        result["reasons"] = ["the right-angled ascending breakout is not confirmed by a close outside the formation"]
        return result
    if (breakout == "UP" and breakout_price <= high) or (breakout == "DOWN" and breakout_price >= low):
        result["reasons"] = ["the confirmed close is not outside the right-angled ascending range"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": breakout_price + height if breakout == "UP" else breakout_price - height, "bulkowski_formation_height": height})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a horizontal-base, rising-top formation produced a confirmed breakout")
