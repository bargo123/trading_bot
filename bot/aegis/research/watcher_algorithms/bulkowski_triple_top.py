"""Bulkowski triple top: three distinct near-equal highs and lower break."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_triple_top"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "779-787"
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
    if normalized_status(first(state, "bulkowski_triple_type")) != "top":
        result["reasons"] = ["this perspective requires a triple top"]
        return result
    if normalized_status(first(state, "bulkowski_triple_timeframe")) not in {"daily", "daily chart", "weekly", "weekly chart", "week"} or None in (*levels, variation, confirmation, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["triple-top levels, timeframe, confirmation, and breakout must be finite observations"]
        return result
    if not 0 <= variation <= 5 or not all(observed_bool(first(state, key)) for key in ("bulkowski_triple_distinct_confirmed", "bulkowski_triple_proportion_confirmed")):
        result["reasons"] = ["three tops must be distinct, similarly proportioned, and near the same price"]
        return result
    if max(levels) - min(levels) > max(abs(max(levels)) * variation / 100, 0.0000001):
        result["reasons"] = ["the three top levels are too far apart for a triple top"]
        return result
    if breakout != "DOWN" or confirmation > low or not observed_bool(first(state, "bulkowski_triple_breakout_close_confirmed")) or price >= confirmation:
        result["reasons"] = ["a triple top requires a confirmed close below the lowest formation low"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_triple_height": height, "bulkowski_measure_target": price - height, "bulkowski_stop_price": high})
    return finish(result, state, "SELL", "three distinct near-equal tops confirmed below their formation support")
