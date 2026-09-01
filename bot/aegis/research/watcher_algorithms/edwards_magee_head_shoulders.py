"""Edwards-Magee head-and-shoulders confirmation proxy."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, first, number, normalized_status, explicitly_confirmed, with_direction

ALGORITHM_ID = "edwards_magee_head_shoulders"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_setup", "em_breakout_direction", "em_breakout_confirmation",
    "em_volume_pattern", "em_neckline_break_pips",
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
    if setup not in {"head shoulders top", "head shoulders bottom"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed sequence is not a confirmed head-and-shoulders formation"]
        return result
    breakout = normalized_status(first(state, "em_breakout_direction"))
    margin = number(first(state, "em_neckline_break_pips"))
    if breakout not in {"up", "down"} or margin is None or margin < 1.0 or not explicitly_confirmed(first(state, "em_breakout_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["the neckline has not been decisively broken and confirmed"]
        return result
    volume_pattern = normalized_status(first(state, "em_volume_pattern"))
    if not any(
        phrase in volume_pattern
        for phrase in (
            "right shoulder lower volume",
            "right shoulder low volume",
            "declining right shoulder volume",
            "volume sequence",
        )
    ):
        result["view"] = "WAIT"
        result["reasons"] = ["the source formation requires a lower-volume right shoulder sequence, not only a geometric shape label"]
        return result
    if not em_real_volume(state):
        result["view"] = "WAIT"
        result["warnings"] = ["tick-volume proxy cannot validate the required volume pattern"]
        result["reasons"] = ["head-and-shoulders confirmation requires source-quality volume evidence"]
        return result
    expected = "down" if setup == "head shoulders top" else "up"
    if breakout != expected:
        result["view"] = "WAIT"
        result["reasons"] = ["neckline break direction contradicts the formation"]
        return result
    return with_direction(result, state, "SELL" if breakout == "down" else "BUY", "confirmed neckline break follows the required reversal structure")
