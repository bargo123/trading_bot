"""Edwards--Magee right-angled broadening breakout study."""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "edwards_magee_broadening_breakout"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_broadening_type",
    "em_broadening_break_direction",
    "em_broadening_break_margin_pct",
    "em_broadening_volume_ratio",
    "em_broadening_confirmation",
    "em_data_provenance",
    "em_volume_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = normalized_status(first(state, "em_broadening_type"))
    break_direction = normalized_status(first(state, "em_broadening_break_direction"))
    margin = number(first(state, "em_broadening_break_margin_pct"))
    volume_ratio = number(first(state, "em_broadening_volume_ratio"))
    if pattern not in {"flat top", "flat bottom", "symmetrical"} or break_direction not in {"up", "down"} or margin is None or volume_ratio is None:
        result["edwards_magee_assessment"] = "INVALID_BROADENING_INPUT"
        result["reasons"] = ["broadening type, break direction, margin, and volume must be finite observed inputs"]
        return result
    if pattern == "symmetrical":
        result["edwards_magee_assessment"] = "SYMMETRICAL_BROADENING_WARNING"
        result["reasons"] = ["symmetrical broadening has unreliable directional breakout evidence at formation"]
        return result
    expected_direction = "up" if pattern == "flat top" else "down"
    if break_direction != expected_direction:
        result["edwards_magee_assessment"] = "BREAK_DIRECTION_CONFLICT"
        result["reasons"] = ["the right-angled broadening boundary and observed break direction conflict"]
        return result
    if margin < 3.0:
        result["edwards_magee_assessment"] = "DECISIVE_MARGIN_NOT_MET"
        result["reasons"] = ["the source's approximate three-percent breakout margin has not been observed"]
        return result
    if not em_real_volume(state) or volume_ratio < 1.2:
        result["edwards_magee_assessment"] = "VOLUME_TEST_FAILED"
        result["warnings"] = ["the source requires conspicuous real volume on a right-angled breakout"]
        return result
    if not explicitly_confirmed(first(state, "em_broadening_confirmation")):
        result["edwards_magee_assessment"] = "BREAKOUT_UNCONFIRMED"
        result["reasons"] = ["the broadening breakout is not explicitly confirmed"]
        return result
    result["edwards_magee_assessment"] = "RIGHT_ANGLED_BROADENING_BREAK"
    return with_direction(result, state, "BUY" if break_direction == "up" else "SELL", "a right-angled broadening boundary was decisively broken with real volume")
