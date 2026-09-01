"""Bulkowski three rising valleys: proportional ascending valleys and upper break."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_three_rising_valleys"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "698-705"
KEYS = (
    "bulkowski_three_valleys_prior_trend", "bulkowski_three_valleys_first",
    "bulkowski_three_valleys_second", "bulkowski_three_valleys_third",
    "bulkowski_three_valleys_proportion_confirmed", "bulkowski_three_valleys_confirmation_level",
    "bulkowski_three_valleys_pattern_high", "bulkowski_three_valleys_pattern_low",
    "bulkowski_three_valleys_breakout_direction", "bulkowski_three_valleys_breakout_close_confirmed",
    "bulkowski_three_valleys_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    valleys = tuple(number(first(state, key)) for key in ("bulkowski_three_valleys_first", "bulkowski_three_valleys_second", "bulkowski_three_valleys_third"))
    confirmation = number(first(state, "bulkowski_three_valleys_confirmation_level"))
    high = number(first(state, "bulkowski_three_valleys_pattern_high"))
    low = number(first(state, "bulkowski_three_valleys_pattern_low"))
    price = number(first(state, "bulkowski_three_valleys_breakout_price"))
    breakout = direction(state, "bulkowski_three_valleys_breakout_direction")
    if normalized_status(first(state, "bulkowski_three_valleys_prior_trend")) not in {"up", "down"} or None in (*valleys, confirmation, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["three rising valleys require a stated trend and finite ordered observations"]
        return result
    if not valleys[0] < valleys[1] < valleys[2] or not observed_bool(first(state, "bulkowski_three_valleys_proportion_confirmed")):
        result["reasons"] = ["the three valleys must rise strictly and remain similarly proportioned"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_three_valleys_breakout_close_confirmed")) or price <= confirmation or price <= high:
        result["reasons"] = ["three rising valleys require a confirmed close above the pattern high"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_three_valleys_height": height, "bulkowski_measure_target": price + height, "bulkowski_stop_price": low})
    return finish(result, state, "BUY", "three proportional valleys rose in sequence and confirmed above resistance")
