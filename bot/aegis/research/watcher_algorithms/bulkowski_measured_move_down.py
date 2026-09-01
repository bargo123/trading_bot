"""Bulkowski measured-move-down first-leg/correction/second-leg perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import finish, observed_bool, start

ALGORITHM_ID = "bulkowski_measured_move_down"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "496-501"
KEYS = (
    "bulkowski_measured_move_type", "bulkowski_mm_first_leg_start", "bulkowski_mm_first_leg_end",
    "bulkowski_mm_corrective_phase_start", "bulkowski_mm_corrective_phase_end",
    "bulkowski_mm_second_leg_current", "bulkowski_mm_corrective_retrace_pct",
    "bulkowski_mm_breakout_confirmed", "bulkowski_mm_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_measured_move_type")) != "down":
        result["reasons"] = ["this perspective requires a measured move down"]
        return result
    first_start = number(first(state, "bulkowski_mm_first_leg_start"))
    first_end = number(first(state, "bulkowski_mm_first_leg_end"))
    correction_start = number(first(state, "bulkowski_mm_corrective_phase_start"))
    correction_end = number(first(state, "bulkowski_mm_corrective_phase_end"))
    second_current = number(first(state, "bulkowski_mm_second_leg_current"))
    retrace = number(first(state, "bulkowski_mm_corrective_retrace_pct"))
    breakout_price = number(first(state, "bulkowski_mm_breakout_price"))
    if None in (first_start, first_end, correction_start, correction_end, second_current, retrace, breakout_price):
        result["reasons"] = ["measured-move legs, correction, and breakout must be finite observations"]
        return result
    height = first_start - first_end
    if height <= 0 or correction_end <= correction_start or not 38 <= retrace <= 62 or second_current >= correction_start or breakout_price >= first_end or not observed_bool(first(state, "bulkowski_mm_breakout_confirmed")):
        result["reasons"] = ["the down move needs a declining first leg, 38-62% upward correction, and confirmed second-leg breakdown"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_first_leg_height": height, "bulkowski_measure_target": correction_end - height / 2})
    return finish(result, state, "SELL", "a declining first leg, measured correction, and confirmed second leg form a measured move down")
