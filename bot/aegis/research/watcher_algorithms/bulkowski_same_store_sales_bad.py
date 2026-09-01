"""Bulkowski bad same-store sales: large high-volume downward reaction."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_same_store_sales_bad"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "908-920"
KEYS = (
    "bulkowski_same_store_type", "bulkowski_same_store_announced", "bulkowski_same_store_range",
    "bulkowski_same_store_month_average_range", "bulkowski_same_store_gap_confirmed",
    "bulkowski_same_store_volume_above_average", "bulkowski_same_store_announcement_high",
    "bulkowski_same_store_announcement_low", "bulkowski_same_store_breakout_direction",
    "bulkowski_same_store_breakout_close_confirmed", "bulkowski_same_store_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    move = number(first(state, "bulkowski_same_store_range"))
    average = number(first(state, "bulkowski_same_store_month_average_range"))
    high = number(first(state, "bulkowski_same_store_announcement_high"))
    low = number(first(state, "bulkowski_same_store_announcement_low"))
    price = number(first(state, "bulkowski_same_store_breakout_price"))
    breakout = direction(state, "bulkowski_same_store_breakout_direction")
    if normalized_status(first(state, "bulkowski_same_store_type")) != "bad" or not observed_bool(first(state, "bulkowski_same_store_announced")) or None in (move, average, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["bad same-store sales require an observed announcement and finite reaction range"]
        return result
    if move <= average and not observed_bool(first(state, "bulkowski_same_store_gap_confirmed")) or not observed_bool(first(state, "bulkowski_same_store_volume_above_average")):
        result["reasons"] = ["bad same-store sales need an above-average move or gap and high volume"]
        return result
    if breakout != "DOWN" or not observed_bool(first(state, "bulkowski_same_store_breakout_close_confirmed")) or price >= low:
        result["reasons"] = ["bad same-store sales require a confirmed close below the announcement low"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_same_store_range": move, "bulkowski_measure_target": price - height, "bulkowski_stop_price": high})
    return finish(result, state, "SELL", "bad same-store sales produced a large high-volume downward reaction and breakout")
