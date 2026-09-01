"""Evidence, validation, provenance, and leakage-control algorithm."""
from __future__ import annotations
from ._common import base, first, number, values

ALGORITHM_ID = "validation_integrity"
SOURCES = ("David Aronson — Evidence-Based Technical Analysis", "Marcos Lopez de Prado — Advances in Financial Machine Learning", "Kevin Davey — Building Winning Algorithmic Trading Systems", "Stefan Jansen — Machine Learning for Algorithmic Trading", "Yves Hilpisch — Python for Finance")
KEYS = ("evidence_n", "sample_size", "oos_n", "validation_status", "calibration_status", "cost_assumptions", "uses_future_data", "provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("sample_and_validation_provenance",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    sample_size = number(first(state, "sample_size", "evidence_n"))
    oos_n = number(first(state, "oos_n"))
    uses_future_data = first(state, "uses_future_data") is True
    cost_assumptions = first(state, "cost_assumptions")
    if uses_future_data:
        assessment = "LEAKAGE_RISK"
    elif oos_n is None or oos_n <= 0:
        assessment = "NO_OOS"
    elif not isinstance(cost_assumptions, dict) or not cost_assumptions:
        assessment = "COSTS_UNSPECIFIED"
    elif sample_size is not None and oos_n > sample_size:
        assessment = "INVALID_COUNTS"
    else:
        assessment = "VALIDATION_CONTEXT"
    result["validation_assessment"] = assessment
    result["directional_claim"] = False
    result["sample_size_observed"] = sample_size
    result["oos_n_observed"] = oos_n
    result["reasons"] = ["validation information is research context, not execution authority"]
    result["warnings"] = ["positive hindsight or in-sample results cannot be treated as live proof"]
    if uses_future_data:
        result["reasons"].append("future-data contamination is explicitly recorded")
    elif assessment == "NO_OOS":
        result["reasons"].append("no positive-size out-of-sample evaluation is recorded")
    elif assessment == "COSTS_UNSPECIFIED":
        result["reasons"].append("cost assumptions are missing or empty")
    elif assessment == "INVALID_COUNTS":
        result["reasons"].append("out-of-sample count exceeds the recorded sample")
    return result
