"""Bulkowski area, breakaway, continuation, and exhaustion gap perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_gap"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "362-369"
KEYS = (
    "bulkowski_gap_type", "bulkowski_gap_context", "bulkowski_gap_direction",
    "bulkowski_gap_follow_through_confirmed", "bulkowski_gap_breakout_price",
    "bulkowski_data_provenance",
)
TYPES = {"area", "breakaway", "continuation", "exhaustion"}


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    gap_type = normalized_status(first(state, "bulkowski_gap_type"))
    context = normalized_status(first(state, "bulkowski_gap_context"))
    breakout = direction(state, "bulkowski_gap_direction")
    price = number(first(state, "bulkowski_gap_breakout_price"))
    if gap_type not in TYPES or breakout is None or price is None:
        result["reasons"] = ["gap type, direction, and breakout price must be observed"]
        return result
    prior_high = number(first(state, "bulkowski_gap_prior_high"))
    current_low = number(first(state, "bulkowski_gap_current_low"))
    prior_low = number(first(state, "bulkowski_gap_prior_low"))
    current_high = number(first(state, "bulkowski_gap_current_high"))
    if breakout == "UP":
        if prior_high is None or current_low is None or current_low <= prior_high:
            result["reasons"] = ["an upward gap requires the current low to exceed the prior high"]
            return result
        width = current_low - prior_high
    else:
        if prior_low is None or current_high is None or current_high >= prior_low:
            result["reasons"] = ["a downward gap requires the current high to remain below the prior low"]
            return result
        width = prior_low - current_high
    expected_context = {
        "area": {"congestion", "range", "sideways"},
        "breakaway": {"consolidation", "range", "trend start"},
        "continuation": {"trend", "middle of trend"},
        "exhaustion": {"trend end", "trend_end", "end of trend"},
    }[gap_type]
    if context not in expected_context or not observed_bool(first(state, "bulkowski_gap_follow_through_confirmed")):
        result["reasons"] = ["the gap context or post-gap follow-through does not identify the selected gap family"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_gap_width": width, "bulkowski_measure_target": price + width if breakout == "UP" else price - width})
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", f"a confirmed {gap_type} gap has executable directional separation")
