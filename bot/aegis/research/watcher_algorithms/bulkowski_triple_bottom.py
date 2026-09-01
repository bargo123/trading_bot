"""Bulkowski triple bottom: three distinct near-equal lows and upper break."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_triple_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "765-772"
KEYS = (
    "bulkowski_triple_type", "bulkowski_triple_prior_trend", "bulkowski_triple_timeframe",
    "bulkowski_triple_first", "bulkowski_triple_second", "bulkowski_triple_third",
    "bulkowski_triple_level_variation_pct", "bulkowski_triple_distinct_confirmed",
    "bulkowski_triple_proportion_confirmed", "bulkowski_triple_confirmation_level",
    "bulkowski_triple_high", "bulkowski_triple_low", "bulkowski_triple_breakout_direction",
    "bulkowski_triple_breakout_close_confirmed", "bulkowski_triple_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    levels = tuple(number(first(state, key)) for key in ("bulkowski_triple_first", "bulkowski_triple_second", "bulkowski_triple_third"))
    variation = number(first(state, "bulkowski_triple_level_variation_pct"))
    confirmation = number(first(state, "bulkowski_triple_confirmation_level"))
    high = number(first(state, "bulkowski_triple_high"))
    low = number(first(state, "bulkowski_triple_low"))
    price = number(first(state, "bulkowski_triple_breakout_price"))
    breakout = direction(state, "bulkowski_triple_breakout_direction")
    if normalized_status(first(state, "bulkowski_triple_type")) != "bottom":
        result["reasons"] = ["this perspective requires a triple bottom"]
        return result
    if normalized_status(first(state, "bulkowski_triple_timeframe")) not in {"daily", "daily chart", "weekly", "weekly chart", "week"} or None in (*levels, variation, confirmation, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["triple-bottom levels, timeframe, confirmation, and breakout must be finite observations"]
        return result
    if not 0 <= variation <= 5 or not all(observed_bool(first(state, key)) for key in ("bulkowski_triple_distinct_confirmed", "bulkowski_triple_proportion_confirmed")):
        result["reasons"] = ["three bottoms must be distinct, similarly proportioned, and near the same price"]
        return result
    if not (max(levels) - min(levels) <= max(abs(min(levels)) * variation / 100, 0.0000001)):
        result["reasons"] = ["the three bottom levels are too far apart for a triple bottom"]
        return result
    if breakout != "UP" or confirmation < high or not observed_bool(first(state, "bulkowski_triple_breakout_close_confirmed")) or price <= confirmation:
        result["reasons"] = ["a triple bottom requires a confirmed close above the highest formation high"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_triple_height": height, "bulkowski_measure_target": price + height, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "three distinct near-equal bottoms confirmed above their formation resistance")
