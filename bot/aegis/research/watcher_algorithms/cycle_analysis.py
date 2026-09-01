"""Cycle phase context; only an explicitly recorded phase can be directional."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "cycle_analysis"
SOURCES = ("John J. Murphy — Technical Analysis of the Financial Markets", "Yves Hilpisch — Python for Finance")
KEYS = (
    "cycle_state", "cycle_direction", "cycle_period", "cycle_confidence",
    "cycle_observation_n", "cycle_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_cycle_phase",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    phase = strings(state, "cycle_state")
    direction_text = strings(state, "cycle_direction")
    period = number(first(state, "cycle_period"))
    confidence = number(first(state, "cycle_confidence"))
    if None in {period, confidence} or period <= 0 or not 0 <= confidence <= 1:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_cycle_period_and_confidence"]
        return result
    if confidence < 0.5:
        result["view"] = "WAIT"
        result["reasons"] = ["cycle phase confidence is below the research minimum"]
        return result
    if "trough" in phase and "rising" in phase and "up" in direction_text:
        return with_direction(result, state, "BUY", "cycle trough is recorded as rising with sufficient confidence")
    if "peak" in phase and "falling" in phase and "down" in direction_text:
        return with_direction(result, state, "SELL", "cycle peak is recorded as falling with sufficient confidence")
    result["view"] = "WAIT"
    result["reasons"] = ["cycle phase and directional slope are not aligned"]
    return result
