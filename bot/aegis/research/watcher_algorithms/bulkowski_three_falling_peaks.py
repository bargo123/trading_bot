"""Bulkowski three falling peaks: proportional descending peaks and lower break."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_three_falling_peaks"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "684-691"
KEYS = (
    "bulkowski_three_peaks_prior_trend", "bulkowski_three_peaks_first",
    "bulkowski_three_peaks_second", "bulkowski_three_peaks_third",
    "bulkowski_three_peaks_proportion_confirmed", "bulkowski_three_peaks_confirmation_level",
    "bulkowski_three_peaks_pattern_high", "bulkowski_three_peaks_pattern_low",
    "bulkowski_three_peaks_breakout_direction", "bulkowski_three_peaks_breakout_close_confirmed",
    "bulkowski_three_peaks_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    peaks = tuple(number(first(state, key)) for key in ("bulkowski_three_peaks_first", "bulkowski_three_peaks_second", "bulkowski_three_peaks_third"))
    confirmation = number(first(state, "bulkowski_three_peaks_confirmation_level"))
    high = number(first(state, "bulkowski_three_peaks_pattern_high"))
    low = number(first(state, "bulkowski_three_peaks_pattern_low"))
    price = number(first(state, "bulkowski_three_peaks_breakout_price"))
    breakout = direction(state, "bulkowski_three_peaks_breakout_direction")
    if normalized_status(first(state, "bulkowski_three_peaks_prior_trend")) != "up" or None in (*peaks, confirmation, high, low, price) or breakout is None or high <= low:
        result["reasons"] = ["three falling peaks require an upward lead-in and finite ordered observations"]
        return result
    if not peaks[0] > peaks[1] > peaks[2] or not observed_bool(first(state, "bulkowski_three_peaks_proportion_confirmed")):
        result["reasons"] = ["the three peaks must descend strictly and remain similarly proportioned"]
        return result
    if breakout != "DOWN" or not observed_bool(first(state, "bulkowski_three_peaks_breakout_close_confirmed")) or price >= confirmation or price >= low:
        result["reasons"] = ["three falling peaks require a confirmed close below the pattern low"]
        return result
    height = high - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_three_peaks_height": height, "bulkowski_measure_target": price - height, "bulkowski_stop_price": high})
    return finish(result, state, "SELL", "three proportional peaks fell in sequence and confirmed below support")
