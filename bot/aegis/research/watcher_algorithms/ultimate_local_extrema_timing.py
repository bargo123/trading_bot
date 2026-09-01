"""Anna Coulling's local-minimum/local-maximum entry-timing study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_local_extrema_timing"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_extreme_type",
    "ultimate_extreme_zone",
    "ultimate_extreme_confirmed",
    "ultimate_extreme_distance_pips",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


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
    extreme = normalized_status(first(state, "ultimate_extreme_type"))
    zone = normalized_status(first(state, "ultimate_extreme_zone"))
    distance = number(first(state, "ultimate_extreme_distance_pips"))
    if distance is None or distance < 0 or not _truthy(first(state, "ultimate_extreme_confirmed")):
        result["view"] = "WAIT"
        result["ultimate_extreme_assessment"] = "EXTREME_OBSERVATION_INVALID"
        result["reasons"] = ["a confirmed local extreme and finite non-negative distance are required"]
        return result
    if extreme in {"local minimum", "minimum", "low", "local low"} and zone == "support":
        signal = "BUY"
        assessment = "LOCAL_MINIMUM_ENTRY_ZONE"
    elif extreme in {"local maximum", "maximum", "high", "local high"} and zone == "resistance":
        signal = "SELL"
        assessment = "LOCAL_MAXIMUM_ENTRY_ZONE"
    else:
        result["view"] = "WAIT"
        result["ultimate_extreme_assessment"] = "EXTREME_ZONE_MISMATCH"
        result["reasons"] = ["local minimum/support and local maximum/resistance are the source-aligned combinations"]
        return result
    result["ultimate_extreme_assessment"] = assessment
    result["ultimate_extreme_distance_pips"] = distance
    return with_direction(result, state, signal, "the confirmed local extreme is in the source-aligned entry zone")
