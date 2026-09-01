"""The Ultimate Forex Trading System's alternating candle-cascade study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_cascade_exhaustion"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_cascade_directions",
    "ultimate_cascade_leg_sizes",
    "ultimate_cascade_dominant_direction",
    "ultimate_cascade_phase",
    "ultimate_cascade_matured",
    "ultimate_cascade_at_extreme",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


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
    directions = first(state, "ultimate_cascade_directions")
    sizes = first(state, "ultimate_cascade_leg_sizes")
    dominant = normalized_status(first(state, "ultimate_cascade_dominant_direction")).upper()
    phase = normalized_status(first(state, "ultimate_cascade_phase"))
    if not isinstance(directions, (list, tuple)) or not isinstance(sizes, (list, tuple)) or len(directions) < 3 or len(directions) != len(sizes):
        result["view"] = "WAIT"
        result["reasons"] = ["at least three causal cascade legs with matching sizes are required"]
        return result
    directions = [normalized_status(value).upper() for value in directions]
    numeric_sizes = [number(value) for value in sizes]
    if any(value not in {"UP", "DOWN"} for value in directions) or any(value is None or value <= 0 for value in numeric_sizes) or dominant not in {"UP", "DOWN"}:
        result["view"] = "WAIT"
        result["reasons"] = ["cascade directions, sizes, and dominant direction are invalid"]
        return result
    if directions.count(dominant) <= len(directions) / 2:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed cascade has no dominant directional move"]
        return result
    if phase == "matured reversal":
        if not _truthy(first(state, "ultimate_cascade_matured")) or not _truthy(first(state, "ultimate_cascade_at_extreme")):
            result["view"] = "WAIT"
            result["reasons"] = ["a matured reversal requires both maturity and an observed extreme"]
            return result
        if directions[-1] == dominant:
            result["view"] = "WAIT"
            result["reasons"] = ["the cascade has not yet shown a final counter-direction leg"]
            return result
        signal = "SELL" if dominant == "UP" else "BUY"
        reason = "the mature cascade shows exhaustion and a counter-direction leg at an extreme"
    elif phase == "early continuation":
        signal = "BUY" if dominant == "UP" else "SELL"
        reason = "the early cascade is treated as a continuation toward its dominant direction"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["cascade phase is not an explicitly supported early or matured state"]
        return result
    result["ultimate_cascade_dominant_direction"] = dominant
    return with_direction(result, state, signal, reason)
