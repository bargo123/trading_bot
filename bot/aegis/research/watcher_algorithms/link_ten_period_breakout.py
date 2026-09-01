"""Marcel Link's ten-period high/low breakout system."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_ten_period_breakout"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_major_trend_direction",
    "link_breakout_close_distance_pips",
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
    trend = normalized_status(first(state, "link_major_trend_direction")).upper()
    distance = number(first(state, "link_breakout_close_distance_pips"))
    exit_rule = normalized_status(first(state, "link_exit_rule"))
    if candidate_side not in {"BUY", "SELL"} or trend != candidate_side or distance is None:
        result["reasons"] = ["the ten-period break must align with the major trend"]
        return result
    expected_exit = "three bar low" if candidate_side == "BUY" else "three bar high"
    if first(state, "link_breakout_confirmed") is not True or expected_exit not in exit_rule:
        result["reasons"] = ["the breakout or three-period momentum-loss exit rule is not observed"]
        return result
    if (candidate_side == "BUY" and distance <= 0) or (candidate_side == "SELL" and distance >= 0):
        result["reasons"] = ["the close has not broken the prior ten-period extreme"]
        return result
    return with_direction(result, state, candidate_side, "prior ten-period extreme broke in the major-trend direction")
