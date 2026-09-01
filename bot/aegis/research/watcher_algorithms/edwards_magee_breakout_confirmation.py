"""Edwards--Magee decisive breakout confirmation study.

The source treats a penetration as a confirmation only after a close beyond
the pattern/trend boundary by an observed margin.  Upside breakouts also
need the source's volume confirmation; the required margin is supplied by
the copied chart context rather than assumed by the Watcher.
"""
from __future__ import annotations

from ._common import base, em_missing, em_real_volume, explicitly_confirmed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "edwards_magee_breakout_confirmation"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "side",
    "em_confirmation_break_direction",
    "em_confirmation_close_confirmed",
    "em_confirmation_penetration_pct",
    "em_confirmation_required_penetration_pct",
    "em_confirmation_volume_required",
    "em_confirmation_volume_confirmed",
    "em_data_provenance",
    "em_volume_provenance",
)


def _confirmed(value) -> bool:
    return value is True or explicitly_confirmed(value)


def _break_direction(value) -> str | None:
    label = normalized_status(value)
    if label in {"up", "upside", "buy", "long", "breakout up"}:
        return "up"
    if label in {"down", "downside", "sell", "short", "breakout down"}:
        return "down"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    break_direction = _break_direction(first(state, "em_confirmation_break_direction"))
    penetration = number(first(state, "em_confirmation_penetration_pct"))
    required = number(first(state, "em_confirmation_required_penetration_pct"))
    if break_direction is None or penetration is None or required is None or penetration < 0 or required <= 0:
        result["edwards_magee_confirmation_assessment"] = "INVALID_CONFIRMATION_INPUT"
        result["reasons"] = ["break direction and observed penetration thresholds must be finite and positive where required"]
        return result
    if not _confirmed(first(state, "em_confirmation_close_confirmed")):
        result["edwards_magee_confirmation_assessment"] = "CLOSE_NOT_CONFIRMED"
        result["reasons"] = ["the source requires a close in the breakout area before treating penetration as confirmation"]
        return result
    if penetration < required:
        result["edwards_magee_confirmation_assessment"] = "DECISIVE_MARGIN_NOT_MET"
        result["reasons"] = ["the observed breakout margin is below the copied context's required decisive margin"]
        return result
    if volman_truth(first(state, "em_confirmation_volume_required")):
        if not em_real_volume(state):
            result["edwards_magee_confirmation_assessment"] = "REAL_VOLUME_UNAVAILABLE"
            result["reasons"] = ["the breakout's volume test cannot be evaluated from a tick-activity proxy"]
            return result
        if not _confirmed(first(state, "em_confirmation_volume_confirmed")):
            result["edwards_magee_confirmation_assessment"] = "VOLUME_CONFIRMATION_NOT_MET"
            result["reasons"] = ["the required breakout volume confirmation was not observed"]
            return result

    result["edwards_magee_confirmation_assessment"] = "DECISIVE_BREAKOUT_CONFIRMED"
    result["edwards_magee_observed_penetration_pct"] = penetration
    result["edwards_magee_required_penetration_pct"] = required
    return with_direction(
        result,
        state,
        "BUY" if break_direction == "up" else "SELL",
        "the observed close and decisive margin satisfy the Edwards--Magee breakout confirmation study",
    )
