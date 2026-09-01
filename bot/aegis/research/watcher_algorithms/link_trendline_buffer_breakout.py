"""Marcel Link's buffered trendline-break system."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_trendline_buffer_breakout"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_trendline_direction",
    "link_break_distance_ticks",
    "link_breakout_confirmed",
    "link_exit_rule",
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
    candidate_side = side(state)
    direction = normalized_status(first(state, "link_trendline_direction"))
    distance = number(first(state, "link_break_distance_ticks"))
    exit_rule = normalized_status(first(state, "link_exit_rule"))
    if first(state, "link_breakout_confirmed") is not True or distance is None:
        result["reasons"] = ["the buffered trendline break is not confirmed"]
        return result
    if "two consecutive closes" not in exit_rule:
        result["reasons"] = ["the two-consecutive-close trendline exit rule is not recorded"]
        return result
    signal = "BUY" if direction == "down" and distance >= 10 else "SELL" if direction == "up" and distance <= -10 else None
    if signal is None:
        result["reasons"] = ["the trendline has not broken by the required directional buffer"]
        return result
    return with_direction(result, state, signal, "trendline break exceeded the ten-tick noise buffer")
