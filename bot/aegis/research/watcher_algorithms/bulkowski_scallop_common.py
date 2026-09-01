"""Shared observed-shape validation for the four Bulkowski scallop rules."""
from __future__ import annotations

from typing import Any, Mapping

from ._common import first, normalized_status, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

KEYS = (
    "bulkowski_scallop_type", "bulkowski_scallop_prior_trend",
    "bulkowski_scallop_shape_confirmed", "bulkowski_scallop_smooth_confirmed",
    "bulkowski_scallop_start_price", "bulkowski_scallop_peak_price",
    "bulkowski_scallop_bowl_low", "bulkowski_scallop_end_price",
    "bulkowski_scallop_retrace_pct", "bulkowski_scallop_width_days",
    "bulkowski_scallop_proportion_confirmed", "bulkowski_scallop_breakout_direction",
    "bulkowski_scallop_breakout_close_confirmed", "bulkowski_scallop_breakout_price",
    "bulkowski_scallop_high", "bulkowski_scallop_low", "bulkowski_data_provenance",
)


def evaluate_scallop(
    algorithm_id: str,
    state: Mapping[str, Any],
    *,
    expected_type: str,
    expected_trend: str,
    source_pages: str,
    allow_breakout: tuple[str, ...],
    require_retrace: bool = False,
    inverted: bool = False,
):
    result = start(algorithm_id, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    kind = normalized_status(first(state, "bulkowski_scallop_type")).replace(" ", "_")
    trend = normalized_status(first(state, "bulkowski_scallop_prior_trend"))
    breakout = direction(state, "bulkowski_scallop_breakout_direction")
    start_price = number(first(state, "bulkowski_scallop_start_price"))
    peak = number(first(state, "bulkowski_scallop_peak_price"))
    bowl_low = number(first(state, "bulkowski_scallop_bowl_low"))
    end_price = number(first(state, "bulkowski_scallop_end_price"))
    retrace = number(first(state, "bulkowski_scallop_retrace_pct"))
    width = number(first(state, "bulkowski_scallop_width_days"))
    high = number(first(state, "bulkowski_scallop_high"))
    low = number(first(state, "bulkowski_scallop_low"))
    price = number(first(state, "bulkowski_scallop_breakout_price"))
    if kind != expected_type or trend != expected_trend:
        result["reasons"] = [f"this perspective requires a {expected_type} scallop in a {expected_trend} trend"]
        return result
    if None in (start_price, peak, bowl_low, end_price, retrace, width, high, low, price) or breakout is None or width <= 0 or high <= low:
        result["reasons"] = ["scallop shape, proportions, and breakout must be finite observations"]
        return result
    if not all(observed_bool(first(state, key)) for key in ("bulkowski_scallop_shape_confirmed", "bulkowski_scallop_smooth_confirmed", "bulkowski_scallop_proportion_confirmed")):
        result["reasons"] = ["the scallop requires observed shape, smooth-turn, and proportionality checks"]
        return result
    if peak <= max(start_price, end_price) or bowl_low >= min(start_price, end_price):
        result["reasons"] = ["the scallop needs a distinct peak and rounded recession between its ends"]
        return result
    if inverted:
        if not 30 <= retrace <= 70:
            result["reasons"] = ["the inverted scallop retrace should be near the observed fifty-percent guide"]
            return result
    elif require_retrace and not 35 <= retrace <= 75:
        result["reasons"] = ["the scallop retrace is outside the observed proportional range"]
        return result
    if breakout not in allow_breakout or not observed_bool(first(state, "bulkowski_scallop_breakout_close_confirmed")):
        result["reasons"] = ["the selected scallop breakout direction is not confirmed"]
        return result
    if (breakout == "UP" and price <= high) or (breakout == "DOWN" and price >= low):
        result["reasons"] = ["the scallop breakout close is not outside the pattern"]
        return result
    depth = peak - bowl_low
    result.update({
        "source_pages": source_pages,
        "bulkowski_scallop_depth": depth,
        "bulkowski_measure_target": price + depth if breakout == "UP" else price - depth,
        "bulkowski_stop_price": low if breakout == "UP" else high,
    })
    return finish(result, state, "BUY" if breakout == "UP" else "SELL", f"the observed {expected_type.replace('_', ' ')} scallop confirmed a {breakout.lower()} breakout")
