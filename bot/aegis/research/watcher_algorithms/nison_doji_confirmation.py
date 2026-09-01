"""Nison doji transition context with next-session resolution."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_doji_confirmation"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_doji_present",
    "nison_doji_context",
    "nison_doji_confirmation_direction",
    "nison_doji_confirmation_bars",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_doji_present")):
        result["view"] = "WAIT"
        result["reasons"] = ["doji observation is not confirmed"]
        return result
    context = normalized_status(first(state, "nison_doji_context"))
    if any(token in context for token in ("lateral", "range", "sideways")):
        result["view"] = "WAIT"
        result["reasons"] = ["a doji in a lateral range is transition context, not a directional signal"]
        return result
    bars = number(first(state, "nison_doji_confirmation_bars"))
    if bars is None or not 1 <= bars <= 2:
        result["view"] = "WAIT"
        result["reasons"] = ["doji confirmation must arrive in the next one or two sessions"]
        return result
    direction = normalized_status(first(state, "nison_doji_confirmation_direction"))
    if direction in {"up", "bullish", "higher", "higher close"}:
        result["nison_doji_assessment"] = "BULLISH_CONFIRMATION"
        return with_direction(result, state, "BUY", "doji transition resolved upward within two sessions")
    if direction in {"down", "bearish", "lower", "lower close"}:
        result["nison_doji_assessment"] = "BEARISH_CONFIRMATION"
        return with_direction(result, state, "SELL", "doji transition resolved downward within two sessions")
    result["view"] = "WAIT"
    result["reasons"] = ["doji has no directional next-session confirmation"]
    return result
