"""Damir value-health warning for opposing excess and narrow rotations."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, values

ALGORITHM_ID = "damir_value_health_warning"
SOURCES = ("Laurentiu Damir — Price Action Breakdown",)
KEYS = (
    "damir_market_trend",
    "damir_recent_excess_side",
    "damir_rotation_location",
    "damir_current_rotation_narrow",
    "damir_value_health_provenance",
)


def _truth(value: object) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "present", "valid"}


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "damir_value_health_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("damir_value_health_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "damir_market_trend"))
    excess = normalized_status(first(state, "damir_recent_excess_side"))
    location = normalized_status(first(state, "damir_rotation_location"))
    candidate_side = normalized_status(first(state, "side"))
    if trend in {"up", "uptrend", "bull", "bullish"}:
        trend = "uptrend"
    elif trend in {"down", "downtrend", "bear", "bearish"}:
        trend = "downtrend"
    elif trend in {"sideways", "horizontal", "balance", "balanced"}:
        trend = "sideways"
    else:
        result["damir_trend_exhaustion_warning"] = False
        result["reasons"] = ["the value-health trend is unresolved"]
        return result
    if excess not in {"above", "below"} or location not in {"upper", "lower"} or candidate_side not in {"buy", "sell"}:
        result["damir_trend_exhaustion_warning"] = False
        result["reasons"] = ["the value-health warning needs a recognized excess side, rotation location, and candidate side"]
        return result

    narrow = _truth(first(state, "damir_current_rotation_narrow"))
    warning = narrow and (
        (excess == "above" and location == "lower" and candidate_side == "buy" and trend in {"uptrend", "sideways"})
        or (excess == "below" and location == "upper" and candidate_side == "sell" and trend in {"downtrend", "sideways"})
    )
    result["damir_trend_exhaustion_warning"] = warning
    if warning:
        result["view"] = "WAIT"
        result["reasons"] = [
            "do not buy: opposing excess and narrow lower rotations warn that the current value/trend may break"
            if candidate_side == "buy"
            else "do not sell: opposing excess and narrow upper rotations warn that the current value/trend may break"
        ]
    else:
        result["reasons"] = ["no source trend-exhaustion warning is present in the observed value state"]
    return result
