"""Ponsi low-liquidity dead-zone false-break fade."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, ponsi_missing, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_boomerang_fade"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_dead_zone",
    "ponsi_breakout_direction",
    "ponsi_reversal_confirmation",
    "ponsi_open_retest",
    "ponsi_time_remaining_s",
    "ponsi_data_provenance",
)


def evaluate(state):
    missing = ponsi_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    remaining = number(first(state, "ponsi_time_remaining_s"))
    breakout = normalized_status(first(state, "ponsi_breakout_direction"))
    if not volman_truth(first(state, "ponsi_dead_zone")):
        result["view"] = "WAIT"
        result["reasons"] = ["boomerang fade is limited to the low-liquidity dead zone"]
        return result
    if remaining is None or remaining <= 0 or remaining > 7200.0:
        result["view"] = "WAIT"
        result["reasons"] = ["the two-hour dead-zone entry window is not active"]
        return result
    if not volman_truth(first(state, "ponsi_reversal_confirmation")) or not volman_truth(first(state, "ponsi_open_retest")):
        result["view"] = "WAIT"
        result["reasons"] = ["false breakout has not confirmed its return toward the session open"]
        return result
    if breakout == "down":
        return with_direction(result, state, "BUY", "low-liquidity downside break faded after confirmation toward the open")
    if breakout == "up":
        return with_direction(result, state, "SELL", "low-liquidity upside break faded after confirmation toward the open")
    result["view"] = "WAIT"
    result["reasons"] = ["boomerang breakout direction is unresolved"]
    return result
