"""Bulkowski stock downgrade: broker event, large range, and directional break."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_stock_downgrade"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "934-949"
KEYS = (
    "bulkowski_broker_event_announced", "bulkowski_broker_event_range",
    "bulkowski_broker_event_month_average_range", "bulkowski_broker_event_volume_above_average",
    "bulkowski_broker_event_announcement_high", "bulkowski_broker_event_announcement_low",
    "bulkowski_broker_event_breakout_direction", "bulkowski_broker_event_breakout_close_confirmed",
    "bulkowski_broker_event_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    move = number(first(state, "bulkowski_broker_event_range"))
    average = number(first(state, "bulkowski_broker_event_month_average_range"))
    high = number(first(state, "bulkowski_broker_event_announcement_high"))
    low = number(first(state, "bulkowski_broker_event_announcement_low"))
    price = number(first(state, "bulkowski_broker_event_breakout_price"))
    breakout = direction(state, "bulkowski_broker_event_breakout_direction")
    if not observed_bool(first(state, "bulkowski_broker_event_announced")) or None in (move, average, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["a downgrade event and finite announcement range are required"]
        return result
    if move <= average or not observed_bool(first(state, "bulkowski_broker_event_volume_above_average")) or not observed_bool(first(state, "bulkowski_broker_event_breakout_close_confirmed")):
        result["reasons"] = ["a downgrade requires an above-average high-volume reaction and confirmed break"]
        return result
    if (breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low):
        result["reasons"] = ["the downgrade event breakout is not outside its announcement range"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_broker_event_range": move, "bulkowski_measure_target": price + height if breakout == "UP" else price - height, "bulkowski_stop_price": low if breakout == "UP" else high})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a stock downgrade produced a large high-volume directional break")
