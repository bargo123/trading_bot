"""Ponsi first-bounce reaction at a round number after a meaningful extension."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, ponsi_missing, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_round_number_bounce"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_round_number_test",
    "ponsi_extension_from_ma_pips",
    "ponsi_first_bounce",
    "ponsi_reversal_direction",
    "ponsi_entry_confirmation",
    "ponsi_data_provenance",
)


def evaluate(state):
    missing = ponsi_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    extension = number(first(state, "ponsi_extension_from_ma_pips"))
    level = normalized_status(first(state, "ponsi_round_number_test"))
    reversal = normalized_status(first(state, "ponsi_reversal_direction"))
    if extension is None or extension < 20.0:
        result["view"] = "WAIT"
        result["reasons"] = ["round-number setup requires at least the source 20-pip moving-average extension"]
        return result
    if not volman_truth(first(state, "ponsi_first_bounce")) or not volman_truth(first(state, "ponsi_entry_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["only the first confirmed reaction at the round number is eligible"]
        return result
    if level == "support" and reversal == "up":
        return with_direction(result, state, "BUY", "first confirmed bounce from round-number support")
    if level == "resistance" and reversal == "down":
        return with_direction(result, state, "SELL", "first confirmed bounce from round-number resistance")
    result["view"] = "WAIT"
    result["reasons"] = ["round-number level and reversal direction do not agree"]
    return result
