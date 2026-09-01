"""Marcel Link's fast exhaustion / 'can't take the pain' reversal checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_pain_reversal"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_prior_trend",
    "link_exhaustion_move_direction",
    "link_exhaustion_magnitude",
    "link_move_speed",
    "link_volume_relative",
    "link_follow_through_failed",
    "link_stochastic_extreme",
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
    magnitude = number(first(state, "link_exhaustion_magnitude"))
    move = normalized_status(first(state, "link_exhaustion_move_direction"))
    speed = normalized_status(first(state, "link_move_speed"))
    volume = normalized_status(first(state, "link_volume_relative"))
    extreme = normalized_status(first(state, "link_stochastic_extreme"))
    prior = normalized_status(first(state, "link_prior_trend"))
    if magnitude is None or magnitude <= 0 or speed != "fast" or volume not in {"above average", "high"}:
        result["reasons"] = ["the exhaustion move is not fast, extended, and volume-confirmed"]
        return result
    if first(state, "link_follow_through_failed") is not True:
        result["reasons"] = ["the exhaustion spike has not lost follow-through"]
        return result
    candidate_side = side(state)
    signal = None
    if move == "down" and extreme == "oversold" and prior == "down" and candidate_side == "BUY":
        signal = "BUY"
    elif move == "up" and extreme == "overbought" and prior == "up" and candidate_side == "SELL":
        signal = "SELL"
    if signal is None:
        result["reasons"] = ["exhaustion direction, stochastic extreme, prior trend, and side do not align"]
        return result
    return with_direction(result, state, signal, "fast high-volume exhaustion failed to continue and snapped back")
