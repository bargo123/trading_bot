"""Bulkowski island-reversal opposing-gap perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_island_reversal"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "464-470"
KEYS = (
    "bulkowski_island_type", "bulkowski_island_prior_trend", "bulkowski_island_left_gap_direction",
    "bulkowski_island_right_gap_direction", "bulkowski_island_gap_prices_overlap",
    "bulkowski_island_duration_days", "bulkowski_island_breakout_direction",
    "bulkowski_island_breakout_close_confirmed", "bulkowski_island_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    kind = normalized_status(first(state, "bulkowski_island_type"))
    prior = normalized_status(first(state, "bulkowski_island_prior_trend"))
    left = direction(state, "bulkowski_island_left_gap_direction")
    right = direction(state, "bulkowski_island_right_gap_direction")
    breakout = direction(state, "bulkowski_island_breakout_direction")
    duration = number(first(state, "bulkowski_island_duration_days"))
    price = number(first(state, "bulkowski_island_breakout_price"))
    if kind != "reversal" or breakout is None or left is None or right is None or duration is None or price is None:
        result["reasons"] = ["island type, opposing gaps, duration, and breakout must be observed"]
        return result
    bottom = prior == "down" and left == "DOWN" and right == "UP" and breakout == "UP"
    top = prior == "up" and left == "UP" and right == "DOWN" and breakout == "DOWN"
    if not 1 <= duration <= 180 or not (bottom or top) or not observed_bool(first(state, "bulkowski_island_gap_prices_overlap")) or not observed_bool(first(state, "bulkowski_island_breakout_close_confirmed")):
        result["reasons"] = ["the island needs opposing gaps at a shared level and a confirmed reversal breakout"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_island_duration_days": duration})
    return finish(result, state, "BUY" if bottom else "SELL", "opposing gaps at a shared price level isolate a confirmed island reversal")
