"""Bulkowski rounding bottom: a long observed bowl and confirmed upper break."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_rounding_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "595-602"
KEYS = (
    "bulkowski_rounding_type", "bulkowski_rounding_timeframe", "bulkowski_rounding_prior_trend",
    "bulkowski_rounding_shape", "bulkowski_rounding_start_price", "bulkowski_rounding_end_price",
    "bulkowski_rounding_low", "bulkowski_rounding_high", "bulkowski_rounding_end_variation_pct",
    "bulkowski_rounding_curve_confirmed", "bulkowski_rounding_breakout_direction",
    "bulkowski_rounding_breakout_close_confirmed", "bulkowski_rounding_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    start_price = number(first(state, "bulkowski_rounding_start_price"))
    end_price = number(first(state, "bulkowski_rounding_end_price"))
    low = number(first(state, "bulkowski_rounding_low"))
    high = number(first(state, "bulkowski_rounding_high"))
    variation = number(first(state, "bulkowski_rounding_end_variation_pct"))
    breakout_price = number(first(state, "bulkowski_rounding_breakout_price"))
    breakout = direction(state, "bulkowski_rounding_breakout_direction")
    if normalized_status(first(state, "bulkowski_rounding_type")) != "bottom":
        result["reasons"] = ["this perspective requires a rounding bottom"]
        return result
    if normalized_status(first(state, "bulkowski_rounding_timeframe")) not in {"daily", "daily chart", "weekly", "weekly chart", "week"} or normalized_status(first(state, "bulkowski_rounding_shape")) not in {"rounded bowl", "bowl", "saucer"}:
        result["reasons"] = ["a rounding bottom needs a daily or weekly rounded bowl observation"]
        return result
    if None in (start_price, end_price, low, high, variation, breakout_price) or breakout is None or high <= low or low >= min(start_price, end_price):
        result["reasons"] = ["rounding-bottom rims, bowl low, and breakout must be finite and ordered"]
        return result
    if not 0 <= variation <= 5 or not observed_bool(first(state, "bulkowski_rounding_curve_confirmed")):
        result["reasons"] = ["the rounding bottom needs a curved bowl with near-even rims"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_rounding_breakout_close_confirmed")) or breakout_price <= high:
        result["reasons"] = ["a rounding bottom requires a confirmed close above the pattern high"]
        return result
    depth = start_price - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_rounding_depth": depth, "bulkowski_measure_target": breakout_price + depth, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "a curved rounding bowl with near-even rims confirmed above resistance")
