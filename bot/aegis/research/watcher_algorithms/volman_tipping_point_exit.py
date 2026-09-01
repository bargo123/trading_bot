"""Bob Volman's technical tipping-point exit study.

The Watcher records the source's technical invalidation point for research.
It does not place, modify, or close a production order.
"""
from __future__ import annotations

from ._common import absent, base, first, number, normalized_status, side, values, volman_missing


ALGORITHM_ID = "volman_tipping_point_exit"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "side",
    "volman_tipping_point_price",
    "volman_current_exit_price",
    "volman_tipping_point_source",
    "volman_tipping_point_activated",
)


def _explicit_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "confirmed", "observed", "active", "activated"}:
        return True
    if label in {"false", "no", "unconfirmed", "inactive", "not activated"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    candidate_side = side(state)
    level = number(first(state, "volman_tipping_point_price"))
    current = number(first(state, "volman_current_exit_price"))
    source = normalized_status(first(state, "volman_tipping_point_source"))
    activated = _explicit_bool(first(state, "volman_tipping_point_activated"))

    if candidate_side not in {"BUY", "SELL"} or level is None or current is None or activated is None:
        result["volman_tipping_point_action"] = "INVALID_TIPPING_POINT_INPUT"
        result["reasons"] = ["side, executable exit price, tipping-point level, and activation must be explicit finite observations"]
        return result
    if source not in {"pullback low", "pullback high", "technical swing low", "technical swing high", "swing low", "swing high"}:
        result["volman_tipping_point_action"] = "INVALID_TECHNICAL_LEVEL"
        result["reasons"] = ["the tipping point must identify a technical swing or pullback level"]
        return result
    expected_sources = {"BUY": {"pullback low", "technical swing low", "swing low"}, "SELL": {"pullback high", "technical swing high", "swing high"}}
    if source not in expected_sources[candidate_side]:
        result["volman_tipping_point_action"] = "LEVEL_SIDE_MISMATCH"
        result["reasons"] = ["a long invalidation is below a technical low and a short invalidation is above a technical high"]
        return result
    if not activated:
        result["volman_tipping_point_action"] = "WAIT_FOR_ACTIVATION"
        result["reasons"] = ["the source activates a replacement tipping point only after the defining price action is taken out"]
        return result

    breached = current <= level if candidate_side == "BUY" else current >= level
    result["volman_tipping_point_price"] = level
    result["volman_current_exit_price"] = current
    if breached:
        result["volman_tipping_point_action"] = "EXIT_TIPPING_POINT_BREACHED"
        result["reasons"] = ["the executable exit price has crossed the active technical point of trade validity"]
    else:
        result["volman_tipping_point_action"] = "HOLD_VALID_TIPPING_POINT"
        result["reasons"] = ["the active technical point of trade validity remains intact"]
    return result
