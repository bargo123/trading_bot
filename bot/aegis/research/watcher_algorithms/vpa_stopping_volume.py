"""Coulling's stopping-volume reversal sequence."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, explicitly_confirmed, vpa_missing, vpa_real_volume, with_direction

ALGORITHM_ID = "vpa_stopping_volume"
SOURCES = ("Anna Coulling — A Complete Guide To Volume Price Analysis",)
KEYS = (
    "vpa_setup", "vpa_trend", "vpa_lower_wick_ratio", "vpa_close_location",
    "vpa_volume_ratio", "vpa_sequence_bars", "vpa_confirmation",
    "vpa_volume_provenance",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = vpa_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if normalized_status(first(state, "vpa_setup")) != "stopping volume":
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed candle sequence is not stopping volume"]
        return result
    if not vpa_real_volume(state):
        result["warnings"] = ["tick-volume proxy cannot validate stopping volume"]
        result["view"] = "WAIT"
        result["reasons"] = ["real traded volume is unavailable"]
        return result
    trend = normalized_status(first(state, "vpa_trend"))
    wick = number(first(state, "vpa_lower_wick_ratio"))
    volume = number(first(state, "vpa_volume_ratio"))
    sequence = number(first(state, "vpa_sequence_bars"))
    close_location = normalized_status(first(state, "vpa_close_location"))
    if trend != "down" or wick is None or wick < 2.0 or volume is None or volume < 1.2 or sequence is None or sequence < 2 or close_location != "upper half":
        result["view"] = "WAIT"
        result["reasons"] = ["downtrend absorption sequence is incomplete"]
        return result
    if not explicitly_confirmed(first(state, "vpa_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["stopping volume requires a confirming reversal candle"]
        return result
    return with_direction(result, state, "BUY", "deep lower-wick/high-volume sequence is absorbing a downtrend")
