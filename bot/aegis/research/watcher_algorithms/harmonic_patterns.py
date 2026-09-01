"""Harmonic-pattern perspective using validated upstream ratios/labels."""
from __future__ import annotations

from ._common import base, direction, strings, values, with_direction

ALGORITHM_ID = "harmonic_patterns"
SOURCES = (
    "Technical Analysis of the Financial Markets — John J. Murphy",
    "Mastering the Trade — John F. Carter",
)
KEYS = ("harmonic_pattern", "harmonic_direction", "harmonic_confirmation", "harmonic_ratios", "pattern_completion")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("harmonic_pattern_and_ratios",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, *KEYS)
    if any(token in text for token in ("invalid", "failed", "incomplete", "unconfirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["harmonic geometry is not confirmed or has failed"]
        return result
    if not any(token in text for token in ("confirmed", "complete", "completion")):
        result["view"] = "WAIT"
        result["reasons"] = ["harmonic pattern is named without completion confirmation"]
        return result
    signal = direction(text)
    if signal:
        return with_direction(result, state, signal, "confirmed harmonic completion direction is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["harmonic completion has no unambiguous direction"]
    return result
