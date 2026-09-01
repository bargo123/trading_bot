"""Classical chart-pattern confirmation and failure algorithm."""
from __future__ import annotations

from ._common import absent, base, direction, explicitly_confirmed, first, strings, values, with_direction

ALGORITHM_ID = "chart_patterns"
SOURCES = (
    "Thomas Bulkowski — Encyclopedia of Chart Patterns",
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Al Brooks — Reading Price Charts Bar by Bar",
)
KEYS = ("pattern", "chart_pattern", "pattern_state", "pattern_confirmation", "pattern_direction", "pattern_detection_provenance", "breakout_confirmation", "failure_state", "measured_move")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("chart_pattern",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("failed", "false", "busted", "invalid", "unconfirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["pattern failure or invalidation is recorded"]
        result["warnings"] = ["historical pattern labels do not override an observed failure"]
        return result
    for key in ("pattern_confirmation", "breakout_confirmation"):
        value = first(state, key)
        if value is not None and not explicitly_confirmed(value):
            result["view"] = "WAIT"
            result["reasons"] = ["pattern confirmation is explicitly absent or negated"]
            return result
    if not any(token in text for token in ("confirmed", "breakout", "trigger", "retest")):
        result["view"] = "WAIT"
        result["reasons"] = ["pattern is named but confirmation is not recorded"]
        return result
    signal = direction(text)
    if signal is None:
        if any(token in text for token in ("double bottom", "inverse head", "bull flag", "ascending", "cup")):
            signal = "BUY"
        elif any(token in text for token in ("double top", "head and shoulders", "bear flag", "descending")):
            signal = "SELL"
    return with_direction(result, state, signal, "confirmed pattern direction is recorded") if signal else result
