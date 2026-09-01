"""Jack Schwager's return-to-spike-extreme continuation study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_spike_extreme_failure"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_spike_direction",
    "schwager_spike_extreme_penetrated",
    "schwager_spike_age_weeks",
    "schwager_spike_magnitude",
    "schwager_spike_invalidated",
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
    signal = _direction(first(state, "schwager_spike_direction"))
    age = number(first(state, "schwager_spike_age_weeks"))
    magnitude = number(first(state, "schwager_spike_magnitude"))
    if signal is None or age is None or magnitude is None or age <= 0 or magnitude <= 0:
        result["view"] = "WAIT"
        result["schwager_spike_assessment"] = "SPIKE_INPUT_INVALID"
        result["reasons"] = ["spike direction, positive age, and positive magnitude are required"]
        return result
    if not _truthy(first(state, "schwager_spike_extreme_penetrated")):
        result["view"] = "WAIT"
        result["schwager_spike_assessment"] = "EXTREME_NOT_PENETRATED"
        result["reasons"] = ["the prior spike extreme has not been observed as penetrated"]
        return result
    if _truthy(first(state, "schwager_spike_invalidated")):
        result["view"] = "WAIT"
        result["schwager_spike_assessment"] = "SPIKE_SIGNAL_INVALIDATED"
        result["reasons"] = ["the opposite extreme closed back through the failed-signal level"]
        return result
    result["schwager_spike_assessment"] = "SPIKE_EXTREME_PENETRATED"
    result["schwager_spike_age_weeks"] = age
    return with_direction(result, state, signal, "penetration of the prior spike extreme supports continuation beyond it")
