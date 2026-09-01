"""Anna Coulling's tight alternating-bar (solid-wall/sandwich) study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "ultimate_sandwich_pattern"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_sandwich_bar_directions",
    "ultimate_sandwich_tight_range",
    "ultimate_sandwich_straight_range",
    "ultimate_sandwich_break_direction",
    "ultimate_sandwich_break_confirmed",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    directions = first(state, "ultimate_sandwich_bar_directions")
    if not isinstance(directions, (list, tuple)) or not 4 <= len(directions) <= 8:
        result["view"] = "WAIT"
        result["ultimate_sandwich_assessment"] = "BAR_COUNT_INVALID"
        result["reasons"] = ["the source describes a solid wall as four to eight alternating bars"]
        return result
    normalized = [_direction(value) for value in directions]
    if any(value is None for value in normalized) or any(left == right for left, right in zip(normalized, normalized[1:])):
        result["view"] = "WAIT"
        result["ultimate_sandwich_assessment"] = "ALTERNATION_INVALID"
        result["reasons"] = ["sandwich bars must alternate observed bullish and bearish directions"]
        return result
    if not _truthy(first(state, "ultimate_sandwich_tight_range")) or not _truthy(first(state, "ultimate_sandwich_straight_range")):
        result["view"] = "WAIT"
        result["ultimate_sandwich_assessment"] = "RANGE_NOT_SOLID"
        result["reasons"] = ["the alternating bars did not form an observed tight, straight consolidation"]
        return result
    if not _truthy(first(state, "ultimate_sandwich_break_confirmed")):
        result["view"] = "WAIT"
        result["ultimate_sandwich_assessment"] = "BREAK_NOT_CONFIRMED"
        result["reasons"] = ["a directional break must be observed after the solid-wall pattern"]
        return result
    signal = _direction(first(state, "ultimate_sandwich_break_direction"))
    if signal is None:
        result["view"] = "WAIT"
        result["ultimate_sandwich_assessment"] = "BREAK_DIRECTION_INVALID"
        result["reasons"] = ["the confirmed break direction is not explicitly observed"]
        return result
    result["ultimate_sandwich_assessment"] = "QUALIFIED_BREAK"
    result["ultimate_sandwich_bar_count"] = len(normalized)
    return with_direction(result, state, signal, "the observed solid-wall pattern broke in the stated direction")
