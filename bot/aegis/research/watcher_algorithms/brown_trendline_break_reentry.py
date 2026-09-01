"""Brown's QMP-preserved trendline-break re-entry perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "brown_trendline_break_reentry"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_original_qmp_dot",
    "brown_opposite_qmp_dot_present",
    "brown_trendline_break_direction",
    "brown_trendline_break_confirmed",
    "brown_trendline_next_candle_open",
    "brown_trendline_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _false_observed(value) -> bool:
    return value is False or normalized_status(value) in {"false", "no", "absent", "none"}


def _direction(value) -> str | None:
    label = normalized_status(value)
    if label in {"green", "up", "buy", "bullish"}:
        return "BUY"
    if label in {"red", "down", "sell", "bearish"}:
        return "SELL"
    return None


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "qmp" in label and "trendline" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brown_trendline_data_provenance")):
        missing.append("brown_trendline_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    original = _direction(first(state, "brown_original_qmp_dot"))
    broken = normalized_status(first(state, "brown_trendline_break_direction"))
    if original is None or broken not in {"up", "down"}:
        result["brown_trendline_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["the original QMP direction and trendline break direction must be explicit"]
        return result
    if not _false_observed(first(state, "brown_opposite_qmp_dot_present")):
        result["brown_trendline_assessment"] = "THESIS_INVALIDATED"
        result["reasons"] = ["an opposite QMP dot ends the original signal's validity"]
        return result
    if not _truth(first(state, "brown_trendline_break_confirmed")):
        result["brown_trendline_assessment"] = "BREAK_UNCONFIRMED"
        result["reasons"] = ["the trendline break must be confirmed before the second entry is considered"]
        return result
    if not _truth(first(state, "brown_trendline_next_candle_open")):
        result["brown_trendline_assessment"] = "NEXT_CANDLE_NOT_OPEN"
        result["reasons"] = ["the confirmed break is considered at the open of the next candle"]
        return result
    expected = "up" if original == "BUY" else "down"
    if broken != expected:
        result["brown_trendline_assessment"] = "BREAK_DIRECTION_MISMATCH"
        result["reasons"] = ["the confirmed trendline break does not resume the original QMP direction"]
        return result
    result["brown_trendline_assessment"] = "BUY_REENTRY" if original == "BUY" else "SELL_REENTRY"
    return with_direction(result, state, original, "the original QMP thesis remained active and its trendline break confirmed a same-direction re-entry")
