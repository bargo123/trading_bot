"""Jack Schwager's confirmed bull/bear trap perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "schwager_bull_bear_trap"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_original_breakout_direction",
    "schwager_trap_confirmation",
    "schwager_trap_confirmation_observed",
    "schwager_trap_invalidated",
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
    breakout = _direction(first(state, "schwager_original_breakout_direction"))
    confirmation = normalized_status(first(state, "schwager_trap_confirmation"))
    if breakout is None:
        result["view"] = "WAIT"
        result["schwager_trap_assessment"] = "BREAKOUT_DIRECTION_INVALID"
        result["reasons"] = ["the original range breakout direction is not explicitly observed"]
        return result
    if confirmation not in {"initial price", "strong price", "time", "initial price confirmation", "strong price confirmation", "time confirmation"}:
        result["view"] = "WAIT"
        result["schwager_trap_assessment"] = "CONFIRMATION_TYPE_INVALID"
        result["reasons"] = ["trap confirmation must be initial-price, strong-price, or time confirmation"]
        return result
    if not _truthy(first(state, "schwager_trap_confirmation_observed")):
        result["view"] = "WAIT"
        result["schwager_trap_assessment"] = "TRAP_NOT_CONFIRMED"
        result["reasons"] = ["the selected trap confirmation has not been observed"]
        return result
    if _truthy(first(state, "schwager_trap_invalidated")):
        result["view"] = "WAIT"
        result["schwager_trap_assessment"] = "TRAP_INVALIDATED"
        result["reasons"] = ["the market returned to the breakout extreme and invalidated the trap"]
        return result
    signal = "SELL" if breakout == "BUY" else "BUY"
    result["schwager_trap_assessment"] = "BULL_TRAP_CONFIRMED" if breakout == "BUY" else "BEAR_TRAP_CONFIRMED"
    result["schwager_trap_confirmation_type"] = confirmation
    return with_direction(result, state, signal, "the failed range breakout supports the opposite-direction trap trade")
