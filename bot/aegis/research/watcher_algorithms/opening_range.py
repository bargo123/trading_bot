"""Opening-range drive, breakout, and rejection algorithm."""
from __future__ import annotations

from ._common import absent, base, strings, values, with_direction

ALGORITHM_ID = "opening_range"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "John F. Carter — Mastering the Trade",
)
KEYS = ("opening_range_state", "opening_range_breakout", "opening_drive", "initial_balance", "session_open", "opening_gap", "session")


def evaluate(state):
    found = values(state, *KEYS)
    opening_inputs = values(state, "opening_range_state", "opening_range_breakout", "opening_drive", "initial_balance", "opening_gap")
    if not opening_inputs:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("opening_range_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("failed", "rejected", "false", "unconfirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["opening-range break or drive is recorded as failed"]
        return result
    if any(token in text for token in ("drive_up", "breakout_up", "above_range", "bullish")):
        return with_direction(result, state, "BUY", "opening-range drive or breakout is recorded above the range")
    if any(token in text for token in ("drive_down", "breakout_down", "below_range", "bearish")):
        return with_direction(result, state, "SELL", "opening-range drive or breakout is recorded below the range")
    result["view"] = "WAIT"
    result["reasons"] = ["opening range is available without a directional drive or confirmed break"]
    return result
