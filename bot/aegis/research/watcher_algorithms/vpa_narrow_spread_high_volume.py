"""Coulling's narrow-spread/high-volume effort-versus-result warning."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, explicitly_confirmed, vpa_missing, vpa_real_volume, with_direction

ALGORITHM_ID = "vpa_narrow_spread_high_volume"
SOURCES = ("Anna Coulling — A Complete Guide To Volume Price Analysis",)
KEYS = (
    "vpa_setup", "vpa_price_direction", "vpa_spread_pips",
    "vpa_average_spread_pips", "vpa_volume_ratio", "vpa_confirmation",
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
    if normalized_status(first(state, "vpa_setup")) != "narrow spread high volume":
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed candle is not a narrow-spread/high-volume anomaly"]
        return result
    if not vpa_real_volume(state):
        result["warnings"] = ["tick-volume proxy cannot validate a VPA volume anomaly"]
        result["view"] = "WAIT"
        result["reasons"] = ["real traded volume is unavailable"]
        return result
    spread = number(first(state, "vpa_spread_pips"))
    average = number(first(state, "vpa_average_spread_pips"))
    volume = number(first(state, "vpa_volume_ratio"))
    price_direction = normalized_status(first(state, "vpa_price_direction"))
    if spread is None or average is None or average <= 0 or volume is None or price_direction not in {"up", "down"} or spread >= average * 0.75 or volume < 1.5:
        result["view"] = "WAIT"
        result["reasons"] = ["narrow spread with unusually high effort is not confirmed"]
        return result
    if not explicitly_confirmed(first(state, "vpa_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["the VPA warning lacks a confirming candle sequence"]
        return result
    signal = "SELL" if price_direction == "up" else "BUY"
    return with_direction(result, state, signal, "high effort produced little price result and confirmed weakness/strength")
