"""Nison Kagi double-window reversal perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_kagi_double_window"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_kagi_double_window_type",
    "nison_kagi_double_window_trend",
    "nison_kagi_double_window_left_separation",
    "nison_kagi_double_window_right_separation",
    "nison_kagi_double_window_confirmation_direction",
    "nison_kagi_double_window_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_kagi_double_window_left_separation")) or not volman_truth(first(state, "nison_kagi_double_window_right_separation")):
        result["view"] = "WAIT"
        result["reasons"] = ["both Kagi waist/shoulder separations are required"]
        return result
    if not volman_truth(first(state, "nison_kagi_double_window_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["double-window reversal has not broken the confirming level"]
        return result
    pattern = normalized_status(first(state, "nison_kagi_double_window_type"))
    trend = normalized_status(first(state, "nison_kagi_double_window_trend"))
    confirmation = normalized_status(first(state, "nison_kagi_double_window_confirmation_direction"))
    if pattern == "bottom" and trend == "down" and confirmation in {"up", "bullish", "higher"}:
        return with_direction(result, state, "BUY", "Kagi double-window bottom has upside confirmation")
    if pattern == "top" and trend == "up" and confirmation in {"down", "bearish", "lower"}:
        return with_direction(result, state, "SELL", "Kagi double-window top has downside confirmation")
    result["view"] = "WAIT"
    result["reasons"] = ["double-window type, trend, and confirmation do not agree"]
    return result
