"""The 10XROI daily push-pull / hourly confirmation perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "thomas_push_pull_10xroi"
SOURCES = ("The 10XROI Trading System",)
KEYS = (
    "thomas_push_pull_direction",
    "thomas_push_pull_pattern",
    "thomas_momentum_strength",
    "thomas_pullback_to_level",
    "thomas_hourly_confirmation",
    "thomas_level_role",
    "thomas_candle_confirmation",
    "thomas_clear_stop",
    "thomas_session",
    "thomas_target_r_multiple",
    "thomas_data_provenance",
)


def _missing(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "thomas_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("thomas_data_provenance")
    return list(dict.fromkeys(missing))


def evaluate(state):
    missing = _missing(state)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = normalized_status(first(state, "thomas_push_pull_pattern"))
    if "push pull" not in pattern:
        result["view"] = "WAIT"
        result["reasons"] = ["the source push-pull candle pattern is not confirmed"]
        return result
    momentum = normalized_status(first(state, "thomas_momentum_strength"))
    if not any(token in momentum for token in ("strong", "parabolic", "impulsive")):
        result["view"] = "WAIT"
        result["reasons"] = ["the source requires a strong momentum environment"]
        return result
    if not volman_truth(first(state, "thomas_pullback_to_level")):
        result["view"] = "WAIT"
        result["reasons"] = ["price has not pulled back to the source push-pull level"]
        return result
    if not volman_truth(first(state, "thomas_hourly_confirmation")) or not volman_truth(first(state, "thomas_candle_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["the hourly entry and confirming candle are not both present"]
        return result
    if not volman_truth(first(state, "thomas_clear_stop")):
        result["view"] = "WAIT"
        result["reasons"] = ["no clear structural stop area is available"]
        return result
    session = normalized_status(first(state, "thomas_session"))
    if not any(token in session for token in ("london", "new york")):
        result["view"] = "WAIT"
        result["reasons"] = ["the source prefers a London or New York entry window"]
        return result
    target_r = number(first(state, "thomas_target_r_multiple"))
    if target_r is None or target_r < 8.0:
        result["view"] = "WAIT"
        result["reasons"] = ["the source fixed-target geometry is below its 8R exception floor"]
        return result
    direction = normalized_status(first(state, "thomas_push_pull_direction"))
    level = normalized_status(first(state, "thomas_level_role"))
    if direction == "up" and level == "support":
        return with_direction(result, state, "BUY", "strong push-pull momentum returned to confirmed support with hourly entry evidence")
    if direction == "down" and level == "resistance":
        return with_direction(result, state, "SELL", "strong push-pull momentum returned to confirmed resistance with hourly entry evidence")
    result["view"] = "WAIT"
    result["reasons"] = ["push-pull direction and support/resistance role are not aligned"]
    return result
