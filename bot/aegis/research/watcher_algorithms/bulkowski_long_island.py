"""Bulkowski long-island wide-gap continuation/reversal perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_long_island"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "480-484"
KEYS = (
    "bulkowski_long_island_prior_trend", "bulkowski_long_island_left_gap_direction",
    "bulkowski_long_island_right_gap_direction", "bulkowski_long_island_left_gap_width",
    "bulkowski_long_island_right_gap_width", "bulkowski_long_island_gaps_aligned",
    "bulkowski_long_island_duration_days", "bulkowski_long_island_breakout_direction",
    "bulkowski_long_island_breakout_close_confirmed", "bulkowski_long_island_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    left = direction(state, "bulkowski_long_island_left_gap_direction")
    right = direction(state, "bulkowski_long_island_right_gap_direction")
    breakout = direction(state, "bulkowski_long_island_breakout_direction")
    left_width = number(first(state, "bulkowski_long_island_left_gap_width"))
    right_width = number(first(state, "bulkowski_long_island_right_gap_width"))
    duration = number(first(state, "bulkowski_long_island_duration_days"))
    price = number(first(state, "bulkowski_long_island_breakout_price"))
    if left is None or right is None or breakout is None or None in (left_width, right_width, duration, price):
        result["reasons"] = ["long-island gap directions, widths, duration, and breakout must be observed"]
        return result
    if left_width < 1 or right_width < 1 or not 1 <= duration < 120 or bool(first(state, "bulkowski_long_island_gaps_aligned")) or right != breakout or left == right or not observed_bool(first(state, "bulkowski_long_island_breakout_close_confirmed")):
        result["reasons"] = ["a long island needs two wide, generally unaligned opposing gaps and a confirmed second-gap breakout"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_long_island_duration_days": duration, "bulkowski_long_island_min_gap_width": min(left_width, right_width)})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a short observed island between two wide opposing gaps confirmed at the second gap")
