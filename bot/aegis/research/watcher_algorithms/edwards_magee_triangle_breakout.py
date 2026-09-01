"""Edwards-Magee triangle compression and breakout proxy."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, first, number, normalized_status, explicitly_confirmed, with_direction

ALGORITHM_ID = "edwards_magee_triangle_breakout"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_setup", "em_breakout_direction", "em_breakout_confirmation",
    "em_triangle_stage", "em_breakout_volume_ratio",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    setup = normalized_status(first(state, "em_setup"))
    if setup not in {"symmetrical triangle", "ascending triangle", "descending triangle"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed compression is not a documented triangle"]
        return result
    stage = normalized_status(first(state, "em_triangle_stage"))
    if stage not in {"half to three quarters", "early"}:
        result["view"] = "WAIT"
        result["reasons"] = ["triangle breakout is too late or its useful completion stage is unresolved"]
        return result
    breakout = normalized_status(first(state, "em_breakout_direction"))
    if breakout not in {"up", "down"} or not explicitly_confirmed(first(state, "em_breakout_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["triangle boundary break is not decisive"]
        return result
    volume = number(first(state, "em_breakout_volume_ratio"))
    if not em_real_volume(state) or volume is None or volume < 1.2:
        result["view"] = "WAIT"
        result["warnings"] = ["triangle breakout in either direction needs real volume confirmation"]
        result["reasons"] = ["breakout effort is not source-quality confirmed"]
        return result
    return with_direction(result, state, "BUY" if breakout == "up" else "SELL", "decisive triangle breakout at a usable completion stage")
