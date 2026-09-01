"""Nison three-line-break black-shoe/white-suit/neck perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_three_line_neck"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_three_line_neck_sequence",
    "nison_three_line_neck_small_line",
    "nison_three_line_neck_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_three_line_neck_small_line")):
        result["view"] = "WAIT"
        result["reasons"] = ["the neck/shoe line is not observed as small"]
        return result
    if not volman_truth(first(state, "nison_three_line_neck_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["three-line neck sequence lacks confirmation"]
        return result
    sequence = normalized_status(first(state, "nison_three_line_neck_sequence"))
    if sequence == "black shoe white suit white neck":
        return with_direction(result, state, "BUY", "black shoe, white suit, and white neck confirm a bullish reversal")
    if sequence == "white neck black suit black shoe":
        return with_direction(result, state, "SELL", "white neck, black suit, and black shoe confirm a bearish reversal")
    result["view"] = "WAIT"
    result["reasons"] = ["observed line sequence is not one of Nison's neck confirmations"]
    return result
