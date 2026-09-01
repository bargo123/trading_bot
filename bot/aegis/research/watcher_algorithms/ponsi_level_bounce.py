"""Evidence-first support/resistance bounce from Forex Patterns & Probabilities."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, ponsi_missing, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_level_bounce"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_level_type",
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
    level = normalized_status(first(state, "ponsi_level_type"))
    reversal = normalized_status(first(state, "ponsi_reversal_direction"))
    if not volman_truth(first(state, "ponsi_first_bounce")):
        result["view"] = "WAIT"
        result["reasons"] = ["Ponsi gives priority to the first evidenced bounce"]
        return result
    if not volman_truth(first(state, "ponsi_entry_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["level was tested but price has not confirmed the move away"]
        return result
    if level == "support" and reversal == "up":
        return with_direction(result, state, "BUY", "price tested support and confirmed a move back above it")
    if level == "resistance" and reversal == "down":
        return with_direction(result, state, "SELL", "price tested resistance and confirmed a move back below it")
    result["view"] = "WAIT"
    result["reasons"] = ["level type and confirmed reversal direction do not agree"]
    return result
