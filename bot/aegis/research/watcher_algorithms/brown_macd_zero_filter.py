"""Brown's QMP-trigger plus MACD-Platinum zero-side filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "brown_macd_zero_filter"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = ("brown_qmp_dot", "brown_macd_platinum_value", "brown_macd_zero_data_provenance")


def _dot_direction(value) -> str | None:
    label = normalized_status(value)
    if label == "green":
        return "BUY"
    if label == "red":
        return "SELL"
    return None


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "qmp" in label and "macd" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_macd_zero_data_provenance")):
        missing.append("brown_macd_zero_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = _dot_direction(first(state, "brown_qmp_dot"))
    value = number(first(state, "brown_macd_platinum_value"))
    if signal is None or value is None:
        result["brown_macd_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["a green/red QMP trigger and finite MACD-Platinum value are required"]
        return result
    if value == 0:
        result["brown_macd_assessment"] = "ZERO_LINE_UNRESOLVED"
        result["reasons"] = ["the zero-side filter has no directional evidence at exactly zero"]
        return result
    if signal == "BUY" and value < 0:
        result["brown_macd_assessment"] = "BELOW_ZERO_BUY_FILTER"
        return with_direction(result, state, "BUY", "the green QMP trigger agrees with MACD Platinum below zero")
    if signal == "SELL" and value > 0:
        result["brown_macd_assessment"] = "ABOVE_ZERO_SELL_FILTER"
        return with_direction(result, state, "SELL", "the red QMP trigger agrees with MACD Platinum above zero")
    result["brown_macd_assessment"] = "QMP_MACD_SIDE_MISMATCH"
    result["reasons"] = ["the QMP trigger is on the opposite side of the source MACD zero filter"]
    return result
