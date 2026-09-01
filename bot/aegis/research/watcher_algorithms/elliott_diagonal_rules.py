"""Frost/Prechter diagonal-motive-wave structural perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "elliott_diagonal_rules"
SOURCES = ("A.J. Frost / Robert R. Prechter — Elliott Wave Principle",)
SOURCE_PAGES = "pp. 93-99"
KEYS = (
    "elliott_diagonal_type",
    "elliott_diagonal_direction",
    "elliott_diagonal_wave_3_not_shortest",
    "elliott_diagonal_structure_confirmed",
    "elliott_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_diagonal_structure",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    diagonal_type = normalized_status(first(state, "elliott_diagonal_type"))
    direction = normalized_status(first(state, "elliott_diagonal_direction"))
    if diagonal_type not in {"leading", "ending"} or direction not in {"up", "uptrend", "bullish", "down", "downtrend", "bearish"}:
        result["view"] = "WAIT"
        result["reasons"] = ["a diagonal must have an observed leading/ending type and unambiguous direction"]
        return result
    if not explicitly_observed(first(state, "elliott_data_provenance"), accepted=("observed", "annotated")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["elliott_data_provenance"]
        return result
    if not volman_truth(first(state, "elliott_diagonal_structure_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["diagonal wedge structure is not confirmed"]
        return result
    if not volman_truth(first(state, "elliott_diagonal_wave_3_not_shortest")):
        result["view"] = "WAIT"
        result["reasons"] = ["wave 3 cannot be the shortest actionary wave in the observed diagonal"]
        return result
    signal = "BUY" if direction in {"up", "uptrend", "bullish"} else "SELL"
    result["elliott_diagonal_assessment"] = f"VALID_{diagonal_type.upper()}_DIAGONAL"
    return with_direction(result, state, signal, "observed diagonal structure preserves its motive direction and wave-three rule")
