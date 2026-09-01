"""Jack Schwager's wide-ranging-day opposite-extreme failure study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "schwager_wide_range_day_failure"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_wide_day_direction",
    "schwager_wide_day_penetration_direction",
    "schwager_wide_day_extreme_penetrated",
    "schwager_wide_day_close_strength",
    "schwager_wide_day_invalidated",
    "schwager_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upside", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downside", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "schwager_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("schwager_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    day = _direction(first(state, "schwager_wide_day_direction"))
    penetration = _direction(first(state, "schwager_wide_day_penetration_direction"))
    strength = normalized_status(first(state, "schwager_wide_day_close_strength"))
    if day is None or penetration is None or not strength:
        result["view"] = "WAIT"
        result["schwager_wide_day_assessment"] = "WIDE_DAY_INPUT_INVALID"
        result["reasons"] = ["wide-day direction, opposite penetration, and close strength are required"]
        return result
    if not _truthy(first(state, "schwager_wide_day_extreme_penetrated")):
        result["view"] = "WAIT"
        result["schwager_wide_day_assessment"] = "EXTREME_NOT_PENETRATED"
        result["reasons"] = ["the opposite extreme of the wide-ranging day has not been penetrated"]
        return result
    if _truthy(first(state, "schwager_wide_day_invalidated")):
        result["view"] = "WAIT"
        result["schwager_wide_day_assessment"] = "WIDE_DAY_SIGNAL_INVALIDATED"
        result["reasons"] = ["the wide-day failure signal has been invalidated"]
        return result
    if day == "SELL" and penetration == "BUY":
        signal = "BUY"
    elif day == "BUY" and penetration == "SELL":
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["schwager_wide_day_assessment"] = "PENETRATION_DIRECTION_INVALID"
        result["reasons"] = ["the failure requires penetration beyond the opposite extreme of the wide-ranging day"]
        return result
    result["schwager_wide_day_assessment"] = "WIDE_DAY_FAILURE_CONFIRMED"
    result["schwager_wide_day_close_strength"] = strength
    return with_direction(result, state, signal, "the opposite-extreme close confirms failure of the wide-ranging day")
