"""Andrew Aziz's Break of High of Day (BHOD) perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "aziz_bhod"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_bhod_level",
    "aziz_bhod_break_direction",
    "aziz_bhod_prior_level_touches",
    "aziz_bhod_break_confirmation",
    "aziz_bhod_pullback_quality",
    "aziz_bhod_volume_confirmation",
    "aziz_bhod_stop_defined",
    "aziz_bhod_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_bhod_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("aziz_bhod_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if str(first(state, "side") or "").upper() != "BUY":
        result["view"] = "WAIT"
        result["reasons"] = ["BHOD is the source's long-side high-of-day perspective"]
        return result
    if number(first(state, "aziz_bhod_level")) is None:
        result["view"] = "WAIT"
        result["reasons"] = ["the high-of-day level is not a valid observed level"]
        return result
    if normalized_status(first(state, "aziz_bhod_break_direction")) not in {"up", "break_up", "breakout_up"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed break is not above the high-of-day level"]
        return result
    touches = number(first(state, "aziz_bhod_prior_level_touches"))
    if touches is None or touches < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["the level has not received the source's repeated prior tests"]
        return result
    checks = (
        ("aziz_bhod_break_confirmation", "the bid has not confirmed a high-of-day break"),
        ("aziz_bhod_volume_confirmation", "increasing-volume confirmation is missing"),
        ("aziz_bhod_stop_defined", "the high-of-day invalidation stop is not defined"),
    )
    for key, reason in checks:
        if not volman_truth(first(state, key)):
            result["view"] = "WAIT"
            result["reasons"] = [reason]
            return result
    pullback = normalized_status(first(state, "aziz_bhod_pullback_quality"))
    if pullback not in {"decent", "good", "strong", "confirmed"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the approach to the high-of-day level lacks a decent pullback"]
        return result
    if first(state, "aziz_bhod_catalyst") is None:
        result["warnings"] = ["news catalyst was not observed; source treats it as a preference, not a hard rule"]
    return with_direction(result, state, "BUY", "repeated high-of-day tests, a confirmed bid break, volume, and pullback quality align")
