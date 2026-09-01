"""Edwards--Magee climactic-volume profit-protection study."""
from __future__ import annotations

from ._common import absent, base, em_missing, em_real_volume, first, number, values, volman_truth

ALGORITHM_ID = "edwards_magee_climactic_volume_stop"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "side",
    "em_climax_volume_ratio",
    "em_climax_prior_peak_volume_ratio",
    "em_climax_extreme_multiple",
    "em_climax_reached_objective",
    "em_climax_outside_trend_channel",
    "em_climax_new_extreme_breakout",
    "em_climax_followthrough_volume",
    "em_data_provenance",
    "em_volume_provenance",
)


def _observed_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    label = str(value or "").strip().lower()
    if label in {"true", "yes", "confirmed", "observed", "present"}:
        return True
    if label in {"false", "no", "unconfirmed", "absent", "not present"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    volume_ratio = number(first(state, "em_climax_volume_ratio"))
    prior_ratio = number(first(state, "em_climax_prior_peak_volume_ratio"))
    extreme_multiple = number(first(state, "em_climax_extreme_multiple"))
    reached_objective = _observed_bool(first(state, "em_climax_reached_objective"))
    outside_channel = _observed_bool(first(state, "em_climax_outside_trend_channel"))
    new_extreme = _observed_bool(first(state, "em_climax_new_extreme_breakout"))
    followthrough = _observed_bool(first(state, "em_climax_followthrough_volume"))
    if (
        volume_ratio is None
        or prior_ratio is None
        or extreme_multiple is None
        or volume_ratio <= 0
        or prior_ratio <= 0
        or extreme_multiple <= 1
        or reached_objective is None
        or outside_channel is None
        or new_extreme is None
        or followthrough is None
    ):
        result["edwards_magee_climax_action"] = "INVALID_CLIMAX_INPUT"
        result["reasons"] = ["volume comparisons, location, and the new-extreme exception must be explicit finite observations"]
        return result
    if not em_real_volume(state):
        result["edwards_magee_climax_action"] = "REAL_VOLUME_UNAVAILABLE"
        result["reasons"] = ["climactic volume cannot be inferred from a tick-activity proxy"]
        return result

    extreme = volume_ratio >= prior_ratio * extreme_multiple
    result["edwards_magee_climax_volume_multiple"] = volume_ratio / prior_ratio
    if not extreme:
        result["edwards_magee_climax_action"] = "CONTINUE"
        result["reasons"] = ["current volume is not conspicuously above the observed prior minor peak volume"]
        return result
    if new_extreme and not followthrough:
        result["edwards_magee_climax_action"] = "NEW_EXTREME_CONTINUATION_EXCEPTION"
        result["reasons"] = ["a new extreme breakout with no subsequent heavy-volume follow-through is not treated as a climax stop trigger"]
        return result
    if not reached_objective and not outside_channel:
        result["edwards_magee_climax_action"] = "CONTINUE"
        result["reasons"] = ["extreme volume alone is insufficient without the source's objective or outside-channel context"]
        return result

    result["edwards_magee_climax_action"] = "PROTECT_PROFIT"
    result["edwards_magee_management_action"] = "RESEARCH_PROGRESSIVE_STOP"
    result["reasons"] = ["climactic volume at a reached objective or outside the trend channel supports a tight profit-protection stop study"]
    return result
