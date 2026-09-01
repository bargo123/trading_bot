"""Nison Renko fixed-brick trend perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_renko_trend"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_renko_direction",
    "nison_renko_bricks",
    "nison_renko_reversal_size_pips",
    "nison_renko_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    bricks = number(first(state, "nison_renko_bricks"))
    reversal = number(first(state, "nison_renko_reversal_size_pips"))
    if bricks is None or bricks < 3 or reversal is None or reversal <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["Renko needs at least three measured bricks and a positive reversal size"]
        return result
    if not volman_truth(first(state, "nison_renko_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["Renko trend has not confirmed the latest brick direction"]
        return result
    direction = normalized_status(first(state, "nison_renko_direction"))
    if direction == "up":
        return with_direction(result, state, "BUY", "confirmed sequence of upward Renko bricks")
    if direction == "down":
        return with_direction(result, state, "SELL", "confirmed sequence of downward Renko bricks")
    result["view"] = "WAIT"
    result["reasons"] = ["Renko direction is unresolved"]
    return result
