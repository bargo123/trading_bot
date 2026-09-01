"""Bulkowski diamond-top widening/narrowing and breakout perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_diamond_top"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "196-199"
KEYS = (
    "bulkowski_diamond_type", "bulkowski_diamond_prior_trend", "bulkowski_diamond_widening_confirmed",
    "bulkowski_diamond_narrowing_confirmed", "bulkowski_diamond_widening_swings",
    "bulkowski_diamond_narrowing_swings", "bulkowski_diamond_breakout_direction",
    "bulkowski_diamond_breakout_close_confirmed", "bulkowski_diamond_breakout_price",
    "bulkowski_diamond_high", "bulkowski_diamond_low", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_diamond_type")) != "top":
        result["reasons"] = ["this perspective requires a diamond top"]
        return result
    widening = number(first(state, "bulkowski_diamond_widening_swings"))
    narrowing = number(first(state, "bulkowski_diamond_narrowing_swings"))
    breakout_price = number(first(state, "bulkowski_diamond_breakout_price"))
    high = number(first(state, "bulkowski_diamond_high"))
    low = number(first(state, "bulkowski_diamond_low"))
    breakout = direction(state, "bulkowski_diamond_breakout_direction")
    if normalized_status(first(state, "bulkowski_diamond_prior_trend")) != "up":
        result["reasons"] = ["a diamond top requires a rising trend into the pattern"]
        return result
    if None in (widening, narrowing, breakout_price, high, low) or breakout is None:
        result["reasons"] = ["diamond swings, breakout, and range must be finite observations"]
        return result
    if not observed_bool(first(state, "bulkowski_diamond_widening_confirmed")) or not observed_bool(first(state, "bulkowski_diamond_narrowing_confirmed")) or widening < 2 or narrowing < 2 or high <= low:
        result["reasons"] = ["a diamond needs observed widening followed by narrowing with at least two swings in each phase"]
        return result
    if not observed_bool(first(state, "bulkowski_diamond_breakout_close_confirmed")) or ((breakout == "UP" and breakout_price <= high) or (breakout == "DOWN" and breakout_price >= low)):
        result["reasons"] = ["the diamond breakout is not a confirmed close outside the formation"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": breakout_price + height if breakout == "UP" else breakout_price - height, "bulkowski_diamond_height": height})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a rising-trend diamond widened, narrowed, and confirmed outside its boundary")
