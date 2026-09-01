"""Observed QPL/Gann entelechy confluence from Oreste's Quantum Trading."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "oreste_entelechy_confluence"
SOURCES = ("Fabio Oreste — Quantum Trading",)
KEYS = (
    "oreste_qpl_level",
    "oreste_gann_angle_level",
    "oreste_current_price",
    "oreste_entelechy_tolerance",
    "oreste_entelechy_interaction",
    "oreste_entelechy_direction",
    "oreste_entelechy_confirmation",
    "oreste_entelechy_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in label for token in ("observed", "timestamped", "measured"))


def _direction(value):
    value = normalized_status(value)
    if value in {"buy", "up", "bull", "bullish", "long"}:
        return "BUY"
    if value in {"sell", "down", "bear", "bearish", "short"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "oreste_entelechy_data_provenance")):
        missing.append("oreste_entelechy_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = True
    qpl = number(first(state, "oreste_qpl_level"))
    angle = number(first(state, "oreste_gann_angle_level"))
    current = number(first(state, "oreste_current_price"))
    tolerance = number(first(state, "oreste_entelechy_tolerance"))
    signal = _direction(first(state, "oreste_entelechy_direction"))
    interaction = normalized_status(first(state, "oreste_entelechy_interaction"))
    if (
        None in {qpl, angle, current, tolerance}
        or tolerance < 0
        or signal is None
        or interaction not in {"reversal", "touch", "rejection", "break", "breakout"}
    ):
        result["oreste_entelechy_assessment"] = "UNKNOWN"
        result["reasons"] = ["entelechy requires two valid levels, proximity, direction, and interaction"]
        return result
    result["oreste_qpl_distance"] = abs(current - qpl)
    result["oreste_gann_distance"] = abs(current - angle)
    if result["oreste_qpl_distance"] > tolerance or result["oreste_gann_distance"] > tolerance:
        result["oreste_entelechy_assessment"] = "NO_CONFLUENCE_PROXIMITY"
        result["reasons"] = ["price is not simultaneously near both supplied confluence levels"]
        return result
    if interaction in {"break", "breakout"}:
        result["oreste_entelechy_assessment"] = "BREAK_REQUIRES_CONTINUATION_RULE"
        result["reasons"] = ["a broken confluence is not treated as a reversal without a separate continuation rule"]
        return result
    if not explicitly_confirmed(first(state, "oreste_entelechy_confirmation")):
        result["oreste_entelechy_assessment"] = "REVERSAL_UNCONFIRMED"
        result["reasons"] = ["two intersecting levels do not prove reversal until observed price action confirms it"]
        return result
    result["oreste_entelechy_assessment"] = "CONFIRMED_REVERSAL"
    return with_direction(result, state, signal, "confirmed price response at a QPL/Gann confluence")

