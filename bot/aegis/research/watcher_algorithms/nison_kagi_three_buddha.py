"""Nison Kagi three-Buddha (head-and-shoulders) reversal perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_kagi_three_buddha"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_kagi_three_buddha_type",
    "nison_kagi_three_buddha_break_direction",
    "nison_kagi_three_buddha_break_levels",
    "nison_kagi_three_buddha_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    levels = number(first(state, "nison_kagi_three_buddha_break_levels"))
    if levels is None or levels < 1 or levels != int(levels):
        result["view"] = "WAIT"
        result["reasons"] = ["Kagi three-Buddha confirmation needs at least a one-level break"]
        return result
    if not volman_truth(first(state, "nison_kagi_three_buddha_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["right Buddha has not been pierced with confirmation"]
        return result
    pattern = normalized_status(first(state, "nison_kagi_three_buddha_type"))
    break_direction = normalized_status(first(state, "nison_kagi_three_buddha_break_direction"))
    if pattern == "top" and break_direction in {"below", "down", "bearish"}:
        return with_direction(result, state, "SELL", "Kagi three-Buddha right shoulder break confirms the top")
    if pattern in {"reverse", "inverted", "reverse top"} and break_direction in {"above", "up", "bullish"}:
        return with_direction(result, state, "BUY", "Kagi reverse three-Buddha right shoulder break confirms the bottom")
    result["view"] = "WAIT"
    result["reasons"] = ["three-Buddha type and right-shoulder break do not agree"]
    return result
