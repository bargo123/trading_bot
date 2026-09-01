"""Nison eight-to-ten record-session exhaustion and confirmation perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_record_sessions"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_record_session_direction",
    "nison_record_session_count",
    "nison_record_session_origin_confirmed",
    "nison_record_session_confirmation_direction",
    "nison_record_session_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_record_session_origin_confirmed")) or not volman_truth(first(state, "nison_record_session_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["record-session count needs a confirmed move origin and reversal confirmation"]
        return result
    count = number(first(state, "nison_record_session_count"))
    if count is None or count != int(count) or not 8 <= count <= 10:
        result["view"] = "WAIT"
        result["reasons"] = ["record-session reversal window is eight to ten records"]
        return result
    record_direction = normalized_status(first(state, "nison_record_session_direction"))
    confirmation = normalized_status(first(state, "nison_record_session_confirmation_direction"))
    if record_direction == "higher highs" and confirmation in {"down", "bearish", "lower"}:
        result["nison_record_session_assessment"] = "RECORD_HIGH_REVERSAL_CONFIRMED"
        return with_direction(result, state, "SELL", "eight-to-ten record highs were followed by downside confirmation")
    if record_direction == "lower lows" and confirmation in {"up", "bullish", "higher"}:
        result["nison_record_session_assessment"] = "RECORD_LOW_REVERSAL_CONFIRMED"
        return with_direction(result, state, "BUY", "eight-to-ten record lows were followed by upside confirmation")
    result["view"] = "WAIT"
    result["reasons"] = ["record-session direction and reversal confirmation do not agree"]
    return result
