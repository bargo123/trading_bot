"""Observed stop-trigger momentum perspective from Harris's text."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "harris_stop_order_momentum"
SOURCES = ("Trading and Exchanges: Market Microstructure for Practitioners",)
KEYS = (
    "harris_stop_triggered",
    "harris_stop_direction",
    "harris_stop_follow_through",
    "harris_stop_order_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("stop" in label or "broker" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "harris_stop_order_provenance")):
        missing.append("harris_stop_order_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    triggered = volman_truth(first(state, "harris_stop_triggered"))
    follow_through = volman_truth(first(state, "harris_stop_follow_through"))
    direction = normalized_status(first(state, "harris_stop_direction")).upper()
    if not triggered:
        result["harris_stop_assessment"] = "NO_TRIGGER"
        result["reasons"] = ["no observed stop activation exists at the decision time"]
        return result
    if direction not in {"BUY", "SELL"}:
        result["harris_stop_assessment"] = "UNKNOWN_DIRECTION"
        result["reasons"] = ["observed stop activation has no unambiguous direction"]
        return result
    if not follow_through:
        result["harris_stop_assessment"] = "NO_FOLLOW_THROUGH"
        result["reasons"] = ["stop activation is not followed by an observed directional move"]
        return result
    result["harris_stop_assessment"] = "MOMENTUM_CONFIRMATION"
    return with_direction(result, state, direction, "observed stop orders are accelerating the confirmed directional move")
