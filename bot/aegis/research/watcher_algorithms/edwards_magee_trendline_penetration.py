"""Edwards--Magee three-test trendline penetration validity study."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "edwards_magee_trendline_penetration"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_trendline_direction",
    "em_trendline_penetration_pips",
    "em_trendline_volume_ratio",
    "em_trendline_post_action",
    "em_trendline_confirmation",
    "em_data_provenance",
    "em_volume_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "em_trendline_direction"))
    penetration = number(first(state, "em_trendline_penetration_pips"))
    volume_ratio = number(first(state, "em_trendline_volume_ratio"))
    post_action = normalized_status(first(state, "em_trendline_post_action"))
    if trend not in {"up", "down"} or penetration is None or volume_ratio is None:
        result["edwards_magee_assessment"] = "INVALID_TRENDLINE_INPUT"
        result["reasons"] = ["trendline direction and penetration/volume measurements must be finite and directional"]
        return result
    if penetration < 1.0:
        result["edwards_magee_assessment"] = "EXTENT_NOT_DECISIVE"
        result["reasons"] = ["the penetration does not clear the observed trendline by a decisive margin"]
        return result
    if not em_real_volume(state) or volume_ratio < 1.2:
        result["edwards_magee_assessment"] = "VOLUME_TEST_FAILED"
        result["warnings"] = ["trendline validity includes volume; real sufficiently elevated volume was not observed"]
        return result
    if post_action not in {"follow through", "held outside", "continued outside", "continuation"}:
        result["edwards_magee_assessment"] = "POST_ACTION_UNRESOLVED"
        result["reasons"] = ["the post-penetration trading action is not observed as follow-through outside the line"]
        return result
    if not explicitly_confirmed(first(state, "em_trendline_confirmation")):
        result["edwards_magee_assessment"] = "PENETRATION_UNCONFIRMED"
        result["reasons"] = ["the trendline penetration is not explicitly confirmed"]
        return result
    result["edwards_magee_assessment"] = "VALID_TRENDLINE_PENETRATION"
    result["edwards_magee_tests_passed"] = ["extent", "volume", "post_action"]
    return with_direction(result, state, "SELL" if trend == "up" else "BUY", "extent, volume, and post-penetration action all validate the trendline break")
