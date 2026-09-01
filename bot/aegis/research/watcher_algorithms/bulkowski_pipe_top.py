"""Bulkowski pipe top: two unusual adjacent upward weekly spikes."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_pipe_top"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "550-553"
KEYS = (
    "bulkowski_pipe_type", "bulkowski_pipe_timeframe", "bulkowski_pipe_prior_trend",
    "bulkowski_pipe_spikes_unusually_large", "bulkowski_pipe_overlap_confirmed",
    "bulkowski_pipe_obvious_confirmed", "bulkowski_pipe_left_high", "bulkowski_pipe_right_high",
    "bulkowski_pipe_low", "bulkowski_pipe_breakout_direction",
    "bulkowski_pipe_breakout_close_confirmed", "bulkowski_pipe_breakout_price",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    highs = (number(first(state, "bulkowski_pipe_left_high")), number(first(state, "bulkowski_pipe_right_high")))
    low = number(first(state, "bulkowski_pipe_low"))
    price = number(first(state, "bulkowski_pipe_breakout_price"))
    breakout = direction(state, "bulkowski_pipe_breakout_direction")
    if normalized_status(first(state, "bulkowski_pipe_type")) != "top" or normalized_status(first(state, "bulkowski_pipe_prior_trend")) != "up":
        result["reasons"] = ["a pipe top requires two upward spikes after a rising trend"]
        return result
    if normalized_status(first(state, "bulkowski_pipe_timeframe")) not in {"weekly", "weekly chart", "week"}:
        result["reasons"] = ["Bulkowski's pipe-top evidence is a weekly-chart formation"]
        return result
    if None in (*highs, low, price) or breakout is None or low >= min(highs):
        result["reasons"] = ["the two pipe highs, pattern low, and breakout must be finite and ordered"]
        return result
    if not all(observed_bool(first(state, key)) for key in ("bulkowski_pipe_spikes_unusually_large", "bulkowski_pipe_overlap_confirmed", "bulkowski_pipe_obvious_confirmed")):
        result["reasons"] = ["pipe spikes must be unusually large, overlapping, and visually obvious"]
        return result
    if breakout != "DOWN" or not observed_bool(first(state, "bulkowski_pipe_breakout_close_confirmed")) or price >= low:
        result["reasons"] = ["a pipe top becomes valid only after a confirmed close below its lowest low"]
        return result
    depth = max(highs) - low
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_pipe_depth": depth, "bulkowski_measure_target": price - depth, "bulkowski_stop_price": max(highs)})
    return finish(result, state, "SELL", "two unusual overlapping upward weekly spikes confirmed below the pipe low")
