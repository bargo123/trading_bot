"""Brown's QMP Filter dot trigger and structural-stop research perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "brown_qmp_filter_trigger"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_qmp_dot",
    "brown_qmp_next_candle_open",
    "brown_qmp_stop_reference",
    "brown_qmp_stop_clearance",
    "brown_qmp_min_stop_clearance",
    "brown_qmp_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _direction(value) -> str | None:
    label = normalized_status(value)
    if label in {"green", "buy", "bull", "bullish"}:
        return "BUY"
    if label in {"red", "sell", "bear", "bearish"}:
        return "SELL"
    return None


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "qmp" in label and any(token in label for token in ("bar", "price", "structure")) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_qmp_data_provenance")):
        missing.append("brown_qmp_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = _direction(first(state, "brown_qmp_dot"))
    clearance = number(first(state, "brown_qmp_stop_clearance"))
    minimum = number(first(state, "brown_qmp_min_stop_clearance"))
    reference = normalized_status(first(state, "brown_qmp_stop_reference"))
    if signal is None or clearance is None or minimum is None or clearance < 0 or minimum <= 0:
        result["brown_qmp_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["QMP dot, positive stop-clearance inputs, and a structural reference are required"]
        return result
    expected_reference = "below recent low" if signal == "BUY" else "above recent high"
    if reference != expected_reference:
        result["brown_qmp_assessment"] = "STOP_REFERENCE_MISMATCH"
        result["reasons"] = ["the protective stop must be beyond the recent low for a buy or recent high for a sell"]
        return result
    if not _truth(first(state, "brown_qmp_next_candle_open")):
        result["brown_qmp_assessment"] = "NEXT_CANDLE_NOT_OPEN"
        result["reasons"] = ["the QMP dot is a trigger for the open of the next candle, not an intrabar hindsight entry"]
        return result
    if clearance < minimum:
        result["brown_qmp_assessment"] = "STOP_CLEARANCE_INSUFFICIENT"
        result["reasons"] = ["the structural stop is not a few observed price units beyond the recent extreme"]
        return result
    result["brown_qmp_assessment"] = "GREEN_DOT_NEXT_CANDLE" if signal == "BUY" else "RED_DOT_NEXT_CANDLE"
    result["brown_qmp_stop_clearance"] = clearance
    return with_direction(result, state, signal, "the observed QMP dot is followed by the next-candle trigger with structural stop room")
