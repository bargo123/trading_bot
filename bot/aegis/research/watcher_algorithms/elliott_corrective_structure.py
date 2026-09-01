"""Frost/Prechter corrective-wave structure perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth

ALGORITHM_ID = "elliott_corrective_structure"
SOURCES = ("A.J. Frost / Robert R. Prechter — Elliott Wave Principle",)
KEYS = (
    "side",
    "elliott_corrective_mode",
    "elliott_corrective_subwave_count",
    "elliott_corrective_type",
    "elliott_corrective_complete",
    "elliott_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("completed_corrective_wave_annotation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    mode = normalized_status(first(state, "elliott_corrective_mode"))
    count = number(first(state, "elliott_corrective_subwave_count"))
    pattern = normalized_status(first(state, "elliott_corrective_type"))
    if mode != "corrective" or count is None or pattern not in {"zigzag", "flat", "triangle"}:
        result["view"] = "WAIT"
        result["reasons"] = ["corrective perspective requires a recognized corrective mode, count, and pattern"]
        return result
    if pattern != "triangle" and count != 3:
        result["view"] = "WAIT"
        result["reasons"] = ["zigzag and flat corrections must have a three-wave top-level structure"]
        return result
    if pattern == "triangle" and count not in {3, 5}:
        result["view"] = "WAIT"
        result["reasons"] = ["triangle correction must use a documented three-wave variation or five-part triangle annotation"]
        return result
    if not volman_truth(first(state, "elliott_corrective_complete")):
        result["view"] = "WAIT"
        result["reasons"] = ["corrective structure is not complete; its termination is less predictable"]
        return result
    if not explicitly_observed(first(state, "elliott_data_provenance"), accepted=("observed", "annotated")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["elliott_data_provenance"]
        return result
    result["elliott_corrective_assessment"] = f"COMPLETED_{pattern.upper()}_CORRECTION"
    result["view"] = "WAIT"
    result["reasons"] = ["completed correction is a structural context signal, not a standalone directional entry"]
    return result
