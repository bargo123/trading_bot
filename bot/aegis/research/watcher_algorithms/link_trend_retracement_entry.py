"""Marcel Link's trend-aligned Fibonacci retracement entry perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_trend_retracement_entry"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "side",
    "link_major_trend_direction",
    "link_retracement_fraction",
    "link_retracement_level_confirmed",
    "link_retracement_support_held",
    "link_retracement_chasing",
    "link_retracement_stop_outside",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "link_major_trend_direction")).upper()
    candidate_side = side(state)
    fraction = number(first(state, "link_retracement_fraction"))
    levels = ((0.382, "38_2_PERCENT"), (0.50, "50_PERCENT"), (0.618, "61_8_PERCENT"))
    level = next((name for value, name in levels if fraction is not None and abs(fraction - value) <= 0.03), None)
    if trend not in {"BUY", "SELL"} or fraction is None or not 0.0 < fraction < 1.0 or level is None:
        result["link_retracement_assessment"] = "INVALID_RETRACEMENT_INPUT"
        result["reasons"] = ["the trend and retracement must match an observed 38.2, 50, or 61.8 percent level"]
        return result
    if candidate_side != trend:
        result["link_retracement_assessment"] = "COUNTERTREND"
        result["reasons"] = ["the retracement entry must follow the observed major trend"]
        return result
    if first(state, "link_retracement_level_confirmed") is not True or first(state, "link_retracement_support_held") is not True:
        result["link_retracement_assessment"] = "PULLBACK_NOT_CONFIRMED"
        result["reasons"] = ["the copied retracement level has not been confirmed as holding support or resistance"]
        return result
    if first(state, "link_retracement_chasing") is not False:
        result["link_retracement_assessment"] = "CHASE_RISK"
        result["reasons"] = ["the source prefers a pullback entry instead of chasing an extended move"]
        return result
    if first(state, "link_retracement_stop_outside") is not True:
        result["link_retracement_assessment"] = "STOP_GEOMETRY_NOT_CONFIRMED"
        result["reasons"] = ["the protective stop is not observed outside the retracement structure"]
        return result

    result.update({"link_retracement_level": level, "link_retracement_fraction": fraction})
    result["link_retracement_assessment"] = "TREND_ALIGNED_PULLBACK_CONFIRMED"
    return with_direction(result, state, candidate_side, "a confirmed pullback at a source-defined retracement level aligns with the major trend")
