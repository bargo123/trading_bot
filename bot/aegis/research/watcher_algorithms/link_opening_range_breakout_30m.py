"""Marcel Link's 30-minute opening-range breakout system."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_opening_range_breakout_30m"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_minutes_since_open",
    "link_opening_range_established",
    "link_opening_range_break_distance_ticks",
    "link_major_trend_direction",
    "link_breakout_close_confirmed",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    minutes = number(first(state, "link_minutes_since_open"))
    distance = number(first(state, "link_opening_range_break_distance_ticks"))
    candidate_side = side(state)
    trend = normalized_status(first(state, "link_major_trend_direction")).upper()
    if minutes is None or minutes <= 30 or first(state, "link_opening_range_established") is not True:
        result["reasons"] = ["the first 30-minute opening range is not complete"]
        return result
    if first(state, "link_breakout_close_confirmed") is not True or trend != candidate_side or distance is None:
        result["reasons"] = ["the opening-range close is not confirmed in the major-trend direction"]
        return result
    if (candidate_side == "BUY" and distance <= 0) or (candidate_side == "SELL" and distance >= 0):
        result["reasons"] = ["price has not broken the corresponding opening-range boundary"]
        return result
    return with_direction(result, state, candidate_side, "30-minute opening range broke with major-trend alignment")
