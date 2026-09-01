"""Bulkowski earnings flag: good-news flagpole, consolidation, and continuation."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_earnings_flag"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "893-906"
KEYS = (
    "bulkowski_earnings_flag_good_earnings_confirmed", "bulkowski_earnings_flag_flagpole_points",
    "bulkowski_earnings_flag_flagpole_days", "bulkowski_earnings_flag_consolidation_confirmed",
    "bulkowski_earnings_flag_duration_days", "bulkowski_earnings_flag_high",
    "bulkowski_earnings_flag_low", "bulkowski_earnings_flag_breakout_direction",
    "bulkowski_earnings_flag_breakout_close_confirmed", "bulkowski_earnings_flag_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    points = number(first(state, "bulkowski_earnings_flag_flagpole_points"))
    pole_days = number(first(state, "bulkowski_earnings_flag_flagpole_days"))
    duration = number(first(state, "bulkowski_earnings_flag_duration_days"))
    high = number(first(state, "bulkowski_earnings_flag_high"))
    low = number(first(state, "bulkowski_earnings_flag_low"))
    price = number(first(state, "bulkowski_earnings_flag_breakout_price"))
    breakout = direction(state, "bulkowski_earnings_flag_breakout_direction")
    if not observed_bool(first(state, "bulkowski_earnings_flag_good_earnings_confirmed")) or None in (points, pole_days, duration, high, low, price) or breakout is None:
        result["reasons"] = ["earnings flagpole, consolidation, and breakout must be finite observations"]
        return result
    if points <= 0 or not 0 < pole_days <= 2 or duration <= 0 or high <= low or not observed_bool(first(state, "bulkowski_earnings_flag_consolidation_confirmed")):
        result["reasons"] = ["the earnings flag needs a fast upward flagpole followed by a distinct consolidation"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_earnings_flag_breakout_close_confirmed")) or price <= high:
        result["reasons"] = ["the earnings flag continuation breakout is not confirmed above the formation"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_earnings_flagpole_points": points, "bulkowski_measure_target": price + points, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "a good-earnings flagpole was followed by consolidation and confirmed upward continuation")
