"""Bulkowski good same-store sales: large high-volume upward reaction."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_same_store_sales_good"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "921-933"
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
    if normalized_status(first(state, "bulkowski_same_store_type")) != "good" or not observed_bool(first(state, "bulkowski_same_store_announced")) or None in (move, average, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["good same-store sales require an observed announcement and finite reaction range"]
        return result
    if move <= average and not observed_bool(first(state, "bulkowski_same_store_gap_confirmed")) or not observed_bool(first(state, "bulkowski_same_store_volume_above_average")):
        result["reasons"] = ["good same-store sales need an above-average move or gap and high volume"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_same_store_breakout_close_confirmed")) or price <= high:
        result["reasons"] = ["good same-store sales require a confirmed close above the announcement high"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_same_store_range": move, "bulkowski_measure_target": price + height, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "good same-store sales produced a large high-volume upward reaction and breakout")
