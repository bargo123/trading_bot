"""Bulkowski horn-bottom two-spike reversal perspective."""
from __future__ import annotations

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_horn_bottom"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "438-444"
KEYS = (
    "bulkowski_horn_type", "bulkowski_horn_prior_trend", "bulkowski_horn_left_extreme",
    "bulkowski_horn_right_extreme", "bulkowski_horn_intervening_extreme", "bulkowski_horn_span_weeks",
    "bulkowski_horn_breakout_direction", "bulkowski_horn_breakout_close_confirmed",
    "bulkowski_horn_breakout_price", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    if normalized_status(first(state, "bulkowski_horn_type")) != "bottom" or normalized_status(first(state, "bulkowski_horn_prior_trend")) != "down":
        result["reasons"] = ["a horn bottom requires a declining prior trend"]
        return result
    left = number(first(state, "bulkowski_horn_left_extreme"))
    right = number(first(state, "bulkowski_horn_right_extreme"))
    middle = number(first(state, "bulkowski_horn_intervening_extreme"))
    span = number(first(state, "bulkowski_horn_span_weeks"))
    price = number(first(state, "bulkowski_horn_breakout_price"))
    breakout = direction(state, "bulkowski_horn_breakout_direction")
    if None in (left, right, middle, span, price) or breakout is None:
        result["reasons"] = ["horn spikes, separation, and breakout must be finite observations"]
        return result
    if not 0.5 <= span <= 2 or not (left < middle and right < middle) or breakout != "UP" or price <= middle or not observed_bool(first(state, "bulkowski_horn_breakout_close_confirmed")):
        result["reasons"] = ["two nearby downward spikes must be separated by a rebound and confirmed upward breakout"]
        return result
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_measure_target": price + (middle - min(left, right)), "bulkowski_horn_depth": middle - min(left, right)})
    return finish(result, state, "BUY", "two nearby downward price spikes formed a horn bottom and broke above the intervening extreme")
