"""Bulkowski pipe bottom: two unusual adjacent downward weekly spikes."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_pipe_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "536-542"
KEYS = (
    "bulkowski_pipe_type", "bulkowski_pipe_timeframe", "bulkowski_pipe_prior_trend",
    "bulkowski_pipe_spikes_unusually_large", "bulkowski_pipe_overlap_confirmed",
    "bulkowski_pipe_obvious_confirmed", "bulkowski_pipe_left_low", "bulkowski_pipe_right_low",
    "bulkowski_pipe_high", "bulkowski_pipe_breakout_direction",
    "bulkowski_pipe_breakout_close_confirmed", "bulkowski_pipe_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    lows = (number(first(state, "bulkowski_pipe_left_low")), number(first(state, "bulkowski_pipe_right_low")))
    high = number(first(state, "bulkowski_pipe_high"))
    price = number(first(state, "bulkowski_pipe_breakout_price"))
    breakout = direction(state, "bulkowski_pipe_breakout_direction")
    if normalized_status(first(state, "bulkowski_pipe_type")) != "bottom" or normalized_status(first(state, "bulkowski_pipe_prior_trend")) != "down":
        result["reasons"] = ["a pipe bottom requires two downward spikes after a declining trend"]
        return result
    if normalized_status(first(state, "bulkowski_pipe_timeframe")) not in {"weekly", "weekly chart", "week"}:
        result["reasons"] = ["Bulkowski's pipe-bottom evidence is a weekly-chart formation"]
        return result
    if None in (*lows, high, price) or breakout is None or high <= max(lows):
        result["reasons"] = ["the two pipe lows, pattern high, and breakout must be finite and ordered"]
        return result
    if not all(observed_bool(first(state, key)) for key in ("bulkowski_pipe_spikes_unusually_large", "bulkowski_pipe_overlap_confirmed", "bulkowski_pipe_obvious_confirmed")):
        result["reasons"] = ["pipe spikes must be unusually large, overlapping, and visually obvious"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_pipe_breakout_close_confirmed")) or price <= high:
        result["reasons"] = ["a pipe bottom becomes valid only after a confirmed close above its highest high"]
        return result
    depth = high - min(lows)
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_pipe_depth": depth, "bulkowski_measure_target": price + depth, "bulkowski_stop_price": min(lows)})
    return finish(result, state, "BUY", "two unusual overlapping downward weekly spikes confirmed above the pipe high")
