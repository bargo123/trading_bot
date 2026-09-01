"""Bulkowski pennant: short converging pause after a steep run."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_pennant"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "522-527"
KEYS = (
    "bulkowski_pennant_trend_direction", "bulkowski_pennant_duration_days",
    "bulkowski_pennant_upper_slope", "bulkowski_pennant_lower_slope",
    "bulkowski_pennant_converging_confirmed", "bulkowski_pennant_preceding_run_points",
    "bulkowski_pennant_breakout_direction", "bulkowski_pennant_breakout_close_confirmed",
    "bulkowski_pennant_breakout_price", "bulkowski_pennant_high", "bulkowski_pennant_low",
    "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    trend = direction(state, "bulkowski_pennant_trend_direction")
    breakout = direction(state, "bulkowski_pennant_breakout_direction")
    duration = number(first(state, "bulkowski_pennant_duration_days"))
    upper = number(first(state, "bulkowski_pennant_upper_slope"))
    lower = number(first(state, "bulkowski_pennant_lower_slope"))
    run = number(first(state, "bulkowski_pennant_preceding_run_points"))
    price = number(first(state, "bulkowski_pennant_breakout_price"))
    high = number(first(state, "bulkowski_pennant_high"))
    low = number(first(state, "bulkowski_pennant_low"))
    if None in (duration, upper, lower, run, price, high, low) or trend is None or breakout is None:
        result["reasons"] = ["pennant run, converging boundaries, and breakout must be finite observations"]
        return result
    if trend not in {"UP", "DOWN"} or not 2 <= duration <= 21 or high <= low or abs(upper - lower) <= 0:
        result["reasons"] = ["a pennant requires a short two-to-twenty-one-day converging pause"]
        return result
    if (trend == "UP" and run <= 0) or (trend == "DOWN" and run >= 0):
        result["reasons"] = ["the pennant must follow a steep run in its prevailing direction"]
        return result
    if not observed_bool(first(state, "bulkowski_pennant_converging_confirmed")):
        result["reasons"] = ["the two pennant boundaries are not observed to converge"]
        return result
    if breakout != trend or not observed_bool(first(state, "bulkowski_pennant_breakout_close_confirmed")):
        result["reasons"] = ["the pennant continuation breakout is not confirmed in the prevailing direction"]
        return result
    if (breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low):
        result["reasons"] = ["the pennant breakout close is not outside its formation"]
        return result
    magnitude = abs(run)
    result.update({
        "source_pages": SOURCE_PAGES,
        "bulkowski_pennant_height": high - low,
        "bulkowski_measure_target": price + magnitude if breakout == "UP" else price - magnitude,
        "bulkowski_stop_price": low if breakout == "UP" else high,
    })
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", "a short converging pennant followed a steep run and confirmed continuation")
