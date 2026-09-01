"""Brown's regular-reversal versus hidden-continuation divergence perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "brown_divergence_type_filter"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_divergence_kind",
    "brown_divergence_direction",
    "brown_divergence_trend",
    "brown_divergence_confirmed",
    "brown_divergence_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "oscillator" in label and "price" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_divergence_data_provenance")):
        missing.append("brown_divergence_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    kind = normalized_status(first(state, "brown_divergence_kind"))
    direction = normalized_status(first(state, "brown_divergence_direction"))
    trend = normalized_status(first(state, "brown_divergence_trend"))
    if kind not in {"regular", "hidden"} or direction not in {"buy", "sell"} or trend not in {"up", "uptrend", "down", "downtrend"}:
        result["brown_divergence_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["regular/hidden type, direction, and prevailing trend must be explicit"]
        return result
    if not _truth(first(state, "brown_divergence_confirmed")):
        result["brown_divergence_assessment"] = "DIVERGENCE_UNCONFIRMED"
        result["reasons"] = ["the divergence is a warning until its price behavior is confirmed"]
        return result
    if kind == "hidden":
        expected = "buy" if trend in {"up", "uptrend"} else "sell"
        if direction != expected:
            result["brown_divergence_assessment"] = "HIDDEN_TREND_MISMATCH"
            result["reasons"] = ["hidden divergence is treated as continuation only in the prevailing trend direction"]
            return result
        result["brown_divergence_assessment"] = "HIDDEN_CONTINUATION"
        return with_direction(result, state, direction.upper(), "confirmed hidden divergence supports continuation of the prevailing trend")
    expected = "buy" if trend in {"down", "downtrend"} else "sell"
    if direction != expected:
        result["brown_divergence_assessment"] = "REGULAR_TREND_NOT_REVERSED"
        result["reasons"] = ["regular divergence is used here as a reversal signal opposite the prevailing trend"]
        return result
    result["brown_divergence_assessment"] = "REGULAR_REVERSAL"
    return with_direction(result, state, direction.upper(), "confirmed regular divergence points to a reversal of the prevailing trend")
