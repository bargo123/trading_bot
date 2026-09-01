"""Coulling's topping-out-volume distribution sequence."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, explicitly_confirmed, vpa_missing, vpa_real_volume, volman_truth, with_direction

ALGORITHM_ID = "vpa_topping_out_volume"
SOURCES = ("Anna Coulling — A Complete Guide To Volume Price Analysis",)
KEYS = (
    "vpa_setup", "vpa_trend", "vpa_upper_wick_ratio", "vpa_spread_contraction",
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
    if normalized_status(first(state, "vpa_setup")) != "topping out volume":
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed candle sequence is not topping-out volume"]
        return result
    if not vpa_real_volume(state):
        result["warnings"] = ["tick-volume proxy cannot validate topping-out volume"]
        result["view"] = "WAIT"
        result["reasons"] = ["real traded volume is unavailable"]
        return result
    trend = normalized_status(first(state, "vpa_trend"))
    wick = number(first(state, "vpa_upper_wick_ratio"))
    volume = number(first(state, "vpa_volume_ratio"))
    sequence = number(first(state, "vpa_sequence_bars"))
    if trend != "up" or wick is None or wick < 2.0 or not volman_truth(first(state, "vpa_spread_contraction")) or volume is None or volume < 1.2 or sequence is None or sequence < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["uptrend distribution sequence is incomplete"]
        return result
    if not explicitly_confirmed(first(state, "vpa_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["topping-out volume requires a confirming shooting-star/weakness sequence"]
        return result
    return with_direction(result, state, "SELL", "deep upper-wick/high-volume sequence is distributing an uptrend")
