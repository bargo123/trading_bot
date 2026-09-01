"""Agustin Silvani's rolling four-hour pivot side filter."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "silvani_rolling_pivot_filter"
SOURCES = ("Beat the Forex Dealer",)
KEYS = (
    "silvani_pivot_high_4h",
    "silvani_pivot_low_4h",
    "silvani_pivot_close_4h",
    "silvani_rolling_pivot",
    "silvani_current_price",
    "silvani_pivot_event",
    "silvani_pivot_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    high = number(first(state, "silvani_pivot_high_4h"))
    low = number(first(state, "silvani_pivot_low_4h"))
    close = number(first(state, "silvani_pivot_close_4h"))
    pivot = number(first(state, "silvani_rolling_pivot"))
    current = number(first(state, "silvani_current_price"))
    missing = [
        key
        for key, value in (
            ("silvani_pivot_high_4h", high),
            ("silvani_pivot_low_4h", low),
            ("silvani_pivot_close_4h", close),
            ("silvani_rolling_pivot", pivot),
            ("silvani_current_price", current),
            ("silvani_pivot_event", first(state, "silvani_pivot_event")),
        )
        if value is None or value == ""
    ]
    provenance = first(state, "silvani_pivot_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped")):
        missing.append("silvani_pivot_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(value is None or value <= 0 for value in (high, low, close, pivot, current)) or high < low:
        result["reasons"] = ["the four-hour OHLC and pivot observations are invalid"]
        return result
    calculated = (high + low + close) / 3.0
    if abs(pivot - calculated) > 1e-10:
        result["reasons"] = ["the rolling pivot is not calculated as (high + low + close) / 3"]
        return result
    if normalized_status(first(state, "silvani_pivot_event")) != "filter not break":
        result["reasons"] = ["the source uses the pivot as a side filter, not as a breakout entry"]
        return result
    side = normalized_status(first(state, "side"))
    signal = "BUY" if side == "buy" and current > pivot else "SELL" if side == "sell" and current < pivot else None
    if signal is None:
        result["reasons"] = ["price is not on the corresponding side of the rolling pivot"]
        return result
    result["silvani_pivot"] = calculated
    result["silvani_pivot_assessment"] = "LONG_SIDE_ALLOWED" if signal == "BUY" else "SHORT_SIDE_ALLOWED"
    return with_direction(result, state, signal, "the observed price is on the source-permitted side of the rolling four-hour pivot")
