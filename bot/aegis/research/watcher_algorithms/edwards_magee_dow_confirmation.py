"""Edwards--Magee confirmation across independent market averages."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "edwards_magee_dow_confirmation"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_average_a_direction",
    "em_average_b_direction",
    "em_dow_confirmation_scope",
    "em_data_provenance",
)


def _trend(value):
    normalized = normalized_status(value)
    if normalized in {"up", "uptrend", "bull", "bullish", "higher"}:
        return "up"
    if normalized in {"down", "downtrend", "bear", "bearish", "lower"}:
        return "down"
    if normalized in {"sideways", "flat", "range", "neutral"}:
        return "sideways"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "em_data_provenance"), accepted=("observed", "timestamped")):
        missing.append("em_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = True
    scope = normalized_status(first(state, "em_dow_confirmation_scope"))
    if scope not in {"two averages", "three indexes", "three averages"}:
        result["edwards_magee_confirmation_assessment"] = "INVALID_CONFIRMATION_SCOPE"
        result["view"] = "WAIT"
        result["reasons"] = ["confirmation must identify the independent averages or indexes being compared"]
        return result

    first_direction = _trend(first(state, "em_average_a_direction"))
    second_direction = _trend(first(state, "em_average_b_direction"))
    result["edwards_magee_average_directions"] = [first_direction, second_direction]
    if first_direction is None or second_direction is None:
        result["edwards_magee_confirmation_assessment"] = "DIRECTION_UNRESOLVED"
        result["view"] = "WAIT"
        result["reasons"] = ["both averages must have an observed up, down, or sideways direction"]
        return result
    if first_direction != second_direction:
        result["edwards_magee_confirmation_assessment"] = "MIXED_AVERAGES"
        result["view"] = "WAIT"
        result["reasons"] = ["one average cannot establish a valid Dow-style change in trend by itself"]
        return result
    if first_direction == "sideways":
        result["edwards_magee_confirmation_assessment"] = "SIDEWAYS_CONFIRMATION"
        result["view"] = "WAIT"
        result["reasons"] = ["the compared averages agree on a non-directional market"]
        return result
    signal = "BUY" if first_direction == "up" else "SELL"
    result["edwards_magee_confirmation_assessment"] = "HARMONIC_CONFIRMATION"
    return with_direction(
        result,
        state,
        signal,
        "the independent market averages confirm the same primary direction",
    )
