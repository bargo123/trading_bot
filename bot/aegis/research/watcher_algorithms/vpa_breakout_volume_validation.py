"""Coulling's volume validation for breaks from price congestion."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, explicitly_confirmed, vpa_missing, vpa_real_volume, volman_truth, with_direction

ALGORITHM_ID = "vpa_breakout_volume_validation"
SOURCES = ("Anna Coulling — A Complete Guide To Volume Price Analysis",)
KEYS = (
    "vpa_setup", "vpa_breakout_direction", "vpa_breakout_confirmation",
    "vpa_clear_water", "vpa_breakout_volume_ratio", "vpa_retest_volume_ratio",
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
    if normalized_status(first(state, "vpa_setup")) != "breakout volume validation":
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed event is not a VPA congestion breakout"]
        return result
    if not vpa_real_volume(state):
        result["warnings"] = ["tick-volume proxy cannot validate a VPA breakout"]
        result["view"] = "WAIT"
        result["reasons"] = ["real traded volume is unavailable"]
        return result
    direction = normalized_status(first(state, "vpa_breakout_direction"))
    breakout_volume = number(first(state, "vpa_breakout_volume_ratio"))
    retest_volume = number(first(state, "vpa_retest_volume_ratio"))
    if direction not in {"up", "down"} or not explicitly_confirmed(first(state, "vpa_breakout_confirmation")) or not volman_truth(first(state, "vpa_clear_water")):
        result["view"] = "WAIT"
        result["reasons"] = ["clear-water breakout confirmation is absent"]
        return result
    if breakout_volume is None or breakout_volume < 1.2 or retest_volume is None or retest_volume > 1.0:
        result["view"] = "WAIT"
        result["reasons"] = ["breakout effort is weak or the retest is not low-volume"]
        return result
    return with_direction(result, state, "BUY" if direction == "up" else "SELL", "clear-water breakout has strong effort and a low-volume retest")
