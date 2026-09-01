"""Edwards--Magee selling-climax bottom and short-term recovery study."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "edwards_magee_selling_climax"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_climax_decline_intensity",
    "em_climax_gap_direction",
    "em_climax_volume_ratio",
    "em_climax_recovery_confirmation",
    "em_data_provenance",
    "em_volume_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    intensity = normalized_status(first(state, "em_climax_decline_intensity"))
    gap_direction = normalized_status(first(state, "em_climax_gap_direction"))
    volume_ratio = number(first(state, "em_climax_volume_ratio"))
    if intensity not in {"panic", "panic decline", "forced selling"} or gap_direction != "down" or volume_ratio is None:
        result["edwards_magee_assessment"] = "INVALID_CLIMAX_INPUT"
        result["reasons"] = ["a selling climax requires a panic-like decline, downside gap, and finite volume observation"]
        return result
    if not em_real_volume(state):
        result["edwards_magee_assessment"] = "SOURCE_VOLUME_UNAVAILABLE"
        result["warnings"] = ["the source requires extreme traded volume; tick activity is not interchangeable"]
        return result
    if volume_ratio < 2.0:
        result["edwards_magee_assessment"] = "EXTREME_VOLUME_NOT_OBSERVED"
        result["reasons"] = ["the decline volume is not extreme relative to the observed baseline"]
        return result
    if not explicitly_confirmed(first(state, "em_climax_recovery_confirmation")):
        result["edwards_magee_assessment"] = "RECOVERY_UNCONFIRMED"
        result["reasons"] = ["a panic decline alone is not a selling climax signal without a confirmed recovery"]
        return result
    result["edwards_magee_assessment"] = "SELLING_CLIMAX_RECOVERY"
    result["edwards_magee_horizon"] = "short_term"
    return with_direction(result, state, "BUY", "a panic-like downside gap and extreme liquidation were followed by a confirmed recovery")
