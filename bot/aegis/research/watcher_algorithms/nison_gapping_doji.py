"""Nison gapping-doji transition with next-session confirmation."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_gapping_doji"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_gapping_doji_trend",
    "nison_gapping_doji_gap_direction",
    "nison_gapping_doji_is_doji",
    "nison_gapping_doji_confirmation_direction",
    "nison_gapping_doji_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_gapping_doji_is_doji")):
        result["view"] = "WAIT"
        result["reasons"] = ["the gapping-doji perspective requires an observed doji, not merely a small candle"]
        return result
    if not volman_truth(first(state, "nison_gapping_doji_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["the gapping doji requires next-session directional confirmation"]
        return result
    trend = normalized_status(first(state, "nison_gapping_doji_trend"))
    gap = normalized_status(first(state, "nison_gapping_doji_gap_direction"))
    confirmation = normalized_status(first(state, "nison_gapping_doji_confirmation_direction"))
    if trend == "falling" and gap == "lower" and confirmation in {"down", "bearish", "lower"}:
        result["nison_gapping_doji_assessment"] = "FALLING_GAPPING_DOJI_CONFIRMED"
        return with_direction(result, state, "SELL", "a lower-gapping doji in a decline received downside follow-through")
    if trend == "rising" and gap == "higher" and confirmation in {"up", "bullish", "higher"}:
        result["nison_gapping_doji_assessment"] = "RISING_GAPPING_DOJI_CONFIRMED"
        return with_direction(result, state, "BUY", "a higher-gapping doji in a rally received upside follow-through")
    result["view"] = "WAIT"
    result["reasons"] = ["gapping-doji trend, gap, and next-session confirmation do not agree"]
    return result
