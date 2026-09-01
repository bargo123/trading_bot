"""Bulkowski FDA approval event: unusually large reaction and confirmed break."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_fda_drug_approval"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "880-892"
KEYS = (
    "bulkowski_fda_approval_announced", "bulkowski_fda_announcement_range",
    "bulkowski_fda_month_average_range", "bulkowski_fda_gap_confirmed",
    "bulkowski_fda_volume_above_average", "bulkowski_fda_announcement_high",
    "bulkowski_fda_announcement_low", "bulkowski_fda_breakout_direction",
    "bulkowski_fda_breakout_close_confirmed", "bulkowski_fda_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    announcement_range = number(first(state, "bulkowski_fda_announcement_range"))
    average_range = number(first(state, "bulkowski_fda_month_average_range"))
    high = number(first(state, "bulkowski_fda_announcement_high"))
    low = number(first(state, "bulkowski_fda_announcement_low"))
    price = number(first(state, "bulkowski_fda_breakout_price"))
    breakout = direction(state, "bulkowski_fda_breakout_direction")
    if not observed_bool(first(state, "bulkowski_fda_approval_announced")) or None in (announcement_range, average_range, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["FDA approval, reaction range, and breakout must be finite observations"]
        return result
    if announcement_range <= average_range and not observed_bool(first(state, "bulkowski_fda_gap_confirmed")):
        result["reasons"] = ["the FDA event needs an above-average move or a confirmed announcement gap"]
        return result
    if not observed_bool(first(state, "bulkowski_fda_volume_above_average")) or not observed_bool(first(state, "bulkowski_fda_breakout_close_confirmed")):
        result["reasons"] = ["the FDA event lacks high-volume and confirmed breakout evidence"]
        return result
    if (breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low):
        result["reasons"] = ["the FDA event breakout is not a confirmed close outside the announcement range"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_fda_range": height, "bulkowski_measure_target": price + height if breakout == "UP" else price - height, "bulkowski_stop_price": low if breakout == "UP" else high})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "an FDA approval produced a large, high-volume reaction and confirmed outside-range break")
