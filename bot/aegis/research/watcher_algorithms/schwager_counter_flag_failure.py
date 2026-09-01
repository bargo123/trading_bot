"""Jack Schwager's counter-to-anticipated flag/pennant breakout study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "schwager_counter_flag_failure"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_flag_prior_swing_direction",
    "schwager_flag_breakout_direction",
    "schwager_flag_breakout_confirmed",
    "schwager_flag_invalidated",
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
    prior = _direction(first(state, "schwager_flag_prior_swing_direction"))
    breakout = _direction(first(state, "schwager_flag_breakout_direction"))
    if prior is None or breakout is None:
        result["view"] = "WAIT"
        result["schwager_flag_assessment"] = "FLAG_DIRECTION_INVALID"
        result["reasons"] = ["prior swing and flag breakout directions are required"]
        return result
    if not _truthy(first(state, "schwager_flag_breakout_confirmed")):
        result["view"] = "WAIT"
        result["schwager_flag_assessment"] = "BREAK_NOT_CONFIRMED"
        result["reasons"] = ["the flag/pennant breakout has not been explicitly confirmed"]
        return result
    if _truthy(first(state, "schwager_flag_invalidated")):
        result["view"] = "WAIT"
        result["schwager_flag_assessment"] = "FLAG_SIGNAL_INVALIDATED"
        result["reasons"] = ["the counter-direction flag signal has been invalidated"]
        return result
    if prior == breakout:
        result["view"] = "WAIT"
        result["schwager_flag_assessment"] = "BREAK_NOT_COUNTER_TO_SWING"
        result["reasons"] = ["the breakout follows, rather than contradicts, the preceding swing"]
        return result
    result["schwager_flag_assessment"] = "COUNTER_BREAK_CONFIRMED"
    return with_direction(result, state, breakout, "the flag/pennant broke opposite the preceding swing as a failed continuation signal")
