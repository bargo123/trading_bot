"""John Carter's multi-timeframe anchor-filtered squeeze study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_anchor_squeeze"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_squeeze_state",
    "carter_squeeze_direction",
    "carter_anchor_direction",
    "carter_wave_c",
    "carter_squeeze_momentum_slope",
    "carter_squeeze_entry_edge",
    "carter_squeeze_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_squeeze_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_squeeze_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    squeeze_state = normalized_status(first(state, "carter_squeeze_state"))
    squeeze_direction = normalized_status(first(state, "carter_squeeze_direction"))
    anchor_direction = normalized_status(first(state, "carter_anchor_direction"))
    wave_c = number(first(state, "carter_wave_c"))
    momentum_slope = number(first(state, "carter_squeeze_momentum_slope"))
    edge = normalized_status(first(state, "carter_squeeze_entry_edge"))
    if squeeze_state not in {"released", "release", "fired", "fire"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the squeeze must be released or fired before this setup is actionable"]
        return result
    if squeeze_direction not in {"up", "upward", "bull", "bullish", "down", "downward", "bear", "bearish"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the lower-timeframe squeeze direction is unresolved"]
        return result
    direction = "BUY" if squeeze_direction in {"up", "upward", "bull", "bullish"} else "SELL"
    expected_anchor = "up" if direction == "BUY" else "down"
    if anchor_direction not in {expected_anchor, "bullish" if direction == "BUY" else "bearish", "upward" if direction == "BUY" else "downward"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the anchor chart forbids fighting the higher-timeframe squeeze direction"]
        return result
    if wave_c is None or (direction == "BUY" and wave_c <= 0) or (direction == "SELL" and wave_c >= 0):
        result["view"] = "WAIT"
        result["reasons"] = ["the source C-wave directional filter does not support the squeeze"]
        return result
    if momentum_slope is None or (direction == "BUY" and momentum_slope <= 0) or (direction == "SELL" and momentum_slope >= 0):
        result["view"] = "WAIT"
        result["reasons"] = ["the squeeze momentum is flat or shifting against the anchor direction"]
        return result
    if edge not in {"near ema", "at ema", "pre release", "pullback", "entry edge"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the squeeze lacks the source's non-chasing entry edge"]
        return result
    result["carter_anchor_filter"] = expected_anchor
    result["carter_squeeze_wave_c"] = wave_c
    return with_direction(result, state, direction, "released squeeze, anchor chart, C-wave, momentum, and entry edge align")
