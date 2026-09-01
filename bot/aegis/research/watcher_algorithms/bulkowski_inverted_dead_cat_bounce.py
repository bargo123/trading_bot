"""Bulkowski inverted dead-cat bounce: positive event, retrace, and recovery."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_inverted_dead_cat_bounce"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "844-854"
KEYS = (
    "bulkowski_idcb_positive_event_confirmed", "bulkowski_idcb_price_gap_up_confirmed",
    "bulkowski_idcb_initial_rise_pct", "bulkowski_idcb_rise_days", "bulkowski_idcb_retrace_pct",
    "bulkowski_idcb_launch_price", "bulkowski_idcb_retrace_low", "bulkowski_idcb_current_price",
    "bulkowski_idcb_higher_high_confirmed", "bulkowski_idcb_recovery_confirmed",
    "bulkowski_idcb_signal_direction", "bulkowski_idcb_signal_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    rise = number(first(state, "bulkowski_idcb_initial_rise_pct"))
    rise_days = number(first(state, "bulkowski_idcb_rise_days"))
    retrace = number(first(state, "bulkowski_idcb_retrace_pct"))
    launch = number(first(state, "bulkowski_idcb_launch_price"))
    retrace_low = number(first(state, "bulkowski_idcb_retrace_low"))
    current = number(first(state, "bulkowski_idcb_current_price"))
    signal_price = number(first(state, "bulkowski_idcb_signal_price"))
    signal = direction(state, "bulkowski_idcb_signal_direction")
    if not all(observed_bool(first(state, key)) for key in ("bulkowski_idcb_positive_event_confirmed", "bulkowski_idcb_price_gap_up_confirmed", "bulkowski_idcb_higher_high_confirmed", "bulkowski_idcb_recovery_confirmed")):
        result["reasons"] = ["an inverted dead-cat bounce needs an observed positive event, gap, retrace, and recovery"]
        return result
    if None in (rise, rise_days, retrace, launch, retrace_low, current, signal_price) or signal is None:
        result["reasons"] = ["inverted dead-cat bounce prices, retrace, and signal must be finite observations"]
        return result
    if rise < 15 or not 1 <= rise_days <= 2 or not 30 <= retrace <= 70 or retrace_low > launch or current <= launch:
        result["reasons"] = ["the positive event must be followed by a substantial short rise, retrace toward launch, and recovery"]
        return result
    if signal != "UP" or signal_price <= launch:
        result["reasons"] = ["the inverted dead-cat recovery has not confirmed an upward signal price"]
        return result
    height = signal_price - launch
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_idcb_height": height, "bulkowski_measure_target": signal_price + height, "bulkowski_stop_price": retrace_low})
    return finish(result, state, "BUY", "a positive event retraced toward its launch and then confirmed recovery")
