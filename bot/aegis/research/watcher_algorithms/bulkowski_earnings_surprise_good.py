"""Bulkowski good earnings surprise: rising trend and confirmed upside break."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_earnings_surprise_good"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "868-878"
KEYS = (
    "bulkowski_earnings_surprise_type", "bulkowski_earnings_prior_trend",
    "bulkowski_earnings_announced", "bulkowski_earnings_announcement_range",
    "bulkowski_earnings_month_average_range", "bulkowski_earnings_announcement_high",
    "bulkowski_earnings_announcement_low", "bulkowski_earnings_breakout_direction",
    "bulkowski_earnings_breakout_close_confirmed", "bulkowski_earnings_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    announcement_range = number(first(state, "bulkowski_earnings_announcement_range"))
    average_range = number(first(state, "bulkowski_earnings_month_average_range"))
    high = number(first(state, "bulkowski_earnings_announcement_high"))
    low = number(first(state, "bulkowski_earnings_announcement_low"))
    price = number(first(state, "bulkowski_earnings_breakout_price"))
    breakout = direction(state, "bulkowski_earnings_breakout_direction")
    if normalized_status(first(state, "bulkowski_earnings_surprise_type")) != "good" or normalized_status(first(state, "bulkowski_earnings_prior_trend")) != "up":
        result["reasons"] = ["a good earnings surprise requires a rising prior trend"]
        return result
    if not observed_bool(first(state, "bulkowski_earnings_announced")) or None in (announcement_range, average_range, high, low, price) or breakout is None:
        result["reasons"] = ["earnings announcement, range, and breakout must be finite observations"]
        return result
    if announcement_range <= average_range or high <= low or breakout != "UP" or not observed_bool(first(state, "bulkowski_earnings_breakout_close_confirmed")) or price <= high:
        result["reasons"] = ["good earnings need an above-average announcement range and confirmed close above its high"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_earnings_range": announcement_range, "bulkowski_measure_target": price + announcement_range, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "a good earnings announcement in a rising trend broke above its wide announcement range")
