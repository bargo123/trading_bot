"""Bulkowski high-and-tight flag momentum continuation perspective."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_high_tight_flag"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "350-352"
KEYS = (
    "bulkowski_htf_prior_rise_pct", "bulkowski_htf_prior_rise_days", "bulkowski_htf_flag_duration_days",
    "bulkowski_htf_flag_retrace_pct", "bulkowski_htf_run_points", "bulkowski_htf_breakout_direction",
    "bulkowski_htf_breakout_close_confirmed", "bulkowski_htf_breakout_price", "bulkowski_htf_flag_low",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    rise = number(first(state, "bulkowski_htf_prior_rise_pct"))
    rise_days = number(first(state, "bulkowski_htf_prior_rise_days"))
    duration = number(first(state, "bulkowski_htf_flag_duration_days"))
    retrace = number(first(state, "bulkowski_htf_flag_retrace_pct"))
    run = number(first(state, "bulkowski_htf_run_points"))
    price = number(first(state, "bulkowski_htf_breakout_price"))
    flag_low = number(first(state, "bulkowski_htf_flag_low"))
    breakout = direction(state, "bulkowski_htf_breakout_direction")
    if None in (rise, rise_days, duration, retrace, run, price, flag_low) or breakout is None:
        result["reasons"] = ["high-tight-flag run, pause, retrace, and breakout must be finite observations"]
        return result
    if rise < 100 or not 0 < rise_days <= 60 or not 1 <= duration <= 35 or not 0 <= retrace <= 20 or run <= 0:
        result["reasons"] = ["the flag must follow at least a doubling within two months and a bounded short consolidation"]
        return result
    if breakout != "UP" or not observed_bool(first(state, "bulkowski_htf_breakout_close_confirmed")):
        result["reasons"] = ["the high-tight flag requires a confirmed upward continuation breakout"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": price + run / 2, "bulkowski_stop_price": flag_low})
    return finish(result, state, "BUY", "a doubling run was followed by a bounded high-tight pause and confirmed continuation breakout")
