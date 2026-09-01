"""Nison Kagi tweezers/double-level reversal perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_kagi_tweezers"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_kagi_tweezers_type",
    "nison_kagi_tweezers_level_match",
    "nison_kagi_tweezers_confirmation_direction",
    "nison_kagi_tweezers_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_kagi_tweezers_level_match")):
        result["view"] = "WAIT"
        result["reasons"] = ["Kagi tweezers do not share a confirmed level"]
        return result
    if not volman_truth(first(state, "nison_kagi_tweezers_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["Kagi tweezers lack reversal confirmation"]
        return result
    pattern = normalized_status(first(state, "nison_kagi_tweezers_type"))
    confirmation = normalized_status(first(state, "nison_kagi_tweezers_confirmation_direction"))
    if pattern == "top" and confirmation in {"down", "bearish", "lower"}:
        return with_direction(result, state, "SELL", "Kagi tweezers top has downside confirmation")
    if pattern == "bottom" and confirmation in {"up", "bullish", "higher"}:
        return with_direction(result, state, "BUY", "Kagi tweezers bottom has upside confirmation")
    result["view"] = "WAIT"
    result["reasons"] = ["tweezers type and reversal confirmation do not agree"]
    return result
