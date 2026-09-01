"""Frost/Prechter's wave-three-beyond-wave-one impulse check."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "elliott_wave_three_extension"
SOURCES = ("A.J. Frost / Robert R. Prechter — Elliott Wave Principle",)
SOURCE_PAGES = "pp. 35-38"
KEYS = (
    "elliott_wave_direction",
    "elliott_wave_3_beyond_wave_1",
    "elliott_wave_structure_confirmed",
    "elliott_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_wave_three_geometry",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "elliott_wave_direction"))
    if direction not in {"up", "uptrend", "bullish", "down", "downtrend", "bearish"}:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["elliott_wave_direction"]
        return result
    if not explicitly_observed(first(state, "elliott_data_provenance"), accepted=("observed", "annotated")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["elliott_data_provenance"]
        return result
    if not volman_truth(first(state, "elliott_wave_structure_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["wave-three geometry is not confirmed from the observed wave labels"]
        return result
    if not volman_truth(first(state, "elliott_wave_3_beyond_wave_1")):
        result["view"] = "WAIT"
        result["reasons"] = ["wave 3 has not traveled beyond the end of wave 1"]
        return result
    signal = "BUY" if direction in {"up", "uptrend", "bullish"} else "SELL"
    result["elliott_wave_three_assessment"] = "WAVE_3_BEYOND_WAVE_1"
    return with_direction(result, state, signal, "observed wave 3 extends beyond wave 1 as required by the source")
