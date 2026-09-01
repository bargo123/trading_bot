"""Observed Quantum Price Line interaction from Oreste's Quantum Trading."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "oreste_qpl_interaction"
SOURCES = ("Fabio Oreste — Quantum Trading",)
KEYS = (
    "oreste_qpl_level",
    "oreste_current_price",
    "oreste_qpl_tolerance",
    "oreste_qpl_role",
    "oreste_qpl_interaction",
    "oreste_qpl_confirmation",
    "oreste_qpl_next_level",
    "oreste_qpl_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in label for token in ("observed", "timestamped", "measured"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "oreste_qpl_data_provenance")):
        missing.append("oreste_qpl_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = True
    level = number(first(state, "oreste_qpl_level"))
    current = number(first(state, "oreste_current_price"))
    tolerance = number(first(state, "oreste_qpl_tolerance"))
    role = normalized_status(first(state, "oreste_qpl_role"))
    interaction = normalized_status(first(state, "oreste_qpl_interaction"))
    if (
        None in {level, current, tolerance}
        or tolerance < 0
        or role not in {"support", "resistance"}
        or interaction not in {"rejection", "reversal", "break", "breakout", "touch"}
    ):
        result["oreste_qpl_assessment"] = "UNKNOWN"
        result["reasons"] = ["QPL interaction requires a valid level, role, price, tolerance, and interaction"]
        return result

    distance = abs(current - level)
    result["oreste_qpl_distance"] = distance
    result["oreste_qpl_target"] = number(first(state, "oreste_qpl_next_level"))
    if distance > tolerance:
        result["oreste_qpl_assessment"] = "NO_PROXIMITY"
        result["reasons"] = ["price is not within the supplied QPL interaction tolerance"]
        return result
    if interaction == "touch":
        result["oreste_qpl_assessment"] = "TOUCH_UNCONFIRMED"
        result["reasons"] = ["a QPL touch is an observation; reversal requires confirmed price action"]
        return result
    if not explicitly_confirmed(first(state, "oreste_qpl_confirmation")):
        result["oreste_qpl_assessment"] = "INTERACTION_UNCONFIRMED"
        result["reasons"] = ["QPL reversal or break is not confirmed by subsequent observed price action"]
        return result

    if interaction in {"break", "breakout"}:
        signal = "SELL" if role == "support" else "BUY"
        reason = "confirmed break of a QPL supports continuation toward the next price level"
        result["oreste_qpl_assessment"] = "CONFIRMED_BREAK"
    else:
        signal = "BUY" if role == "support" else "SELL"
        reason = "confirmed rejection of a QPL supports reversal away from the level"
        result["oreste_qpl_assessment"] = "CONFIRMED_REJECTION"
    return with_direction(result, state, signal, reason)

