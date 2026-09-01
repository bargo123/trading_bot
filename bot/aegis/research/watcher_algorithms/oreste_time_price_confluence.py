"""Time/price agreement perspective from Oreste's Quantum Trading."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, normalized_status, values, with_direction

ALGORITHM_ID = "oreste_time_price_confluence"
SOURCES = ("Fabio Oreste — Quantum Trading",)
KEYS = (
    "oreste_time_signal",
    "oreste_price_signal",
    "oreste_time_direction",
    "oreste_price_direction",
    "oreste_time_confirmation",
    "oreste_price_confirmation",
    "oreste_time_price_agreement",
    "oreste_time_price_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in label for token in ("observed", "timestamped", "measured"))


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "agreed", "present"}


def _direction(value):
    value = normalized_status(value)
    if value in {"buy", "up", "bull", "bullish", "long", "reversal up"}:
        return "BUY"
    if value in {"sell", "down", "bear", "bearish", "short", "reversal down"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "oreste_time_price_data_provenance")):
        missing.append("oreste_time_price_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = True
    time_direction = _direction(first(state, "oreste_time_direction"))
    price_direction = _direction(first(state, "oreste_price_direction"))
    if not _truth(first(state, "oreste_time_price_agreement")):
        result["oreste_time_price_assessment"] = "NO_AGREEMENT"
        result["reasons"] = ["time and price studies are recorded without explicit agreement"]
        return result
    if not explicitly_confirmed(first(state, "oreste_time_confirmation")) or not explicitly_confirmed(first(state, "oreste_price_confirmation")):
        result["oreste_time_price_assessment"] = "CONFIRMATION_MISSING"
        result["reasons"] = ["both time and price observations must be confirmed"]
        return result
    if time_direction is None or price_direction is None or time_direction != price_direction:
        result["oreste_time_price_assessment"] = "DIRECTION_DISAGREEMENT"
        result["reasons"] = ["time and price signals do not agree on a direction"]
        return result
    result["oreste_time_price_assessment"] = "CONFIRMED_CONFLUENCE"
    return with_direction(result, state, time_direction, "confirmed time and price algorithms agree")

