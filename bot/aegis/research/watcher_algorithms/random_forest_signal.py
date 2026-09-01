"""Validated random-forest directional model perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_calibrated, explicitly_validated, first, number, values, with_direction

ALGORITHM_ID = "random_forest_signal"
SOURCES = ("Stefan Jansen — Machine Learning for Algorithmic Trading", "Ernest P. Chan — Machine Trading")
KEYS = ("rf_prediction", "rf_probability", "rf_model_status", "rf_symbol", "rf_horizon_s")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("calibrated_random_forest_prediction",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    prediction = str(first(state, "rf_prediction") or "").strip().upper()
    probability = number(first(state, "rf_probability"))
    status = first(state, "rf_model_status")
    if prediction not in {"BUY", "SELL"} or probability is None or not explicitly_calibrated(status) or not explicitly_validated(status, accepted=("walk forward", "sealed oos", "validated")):
        result["view"] = "WAIT"
        result["reasons"] = ["random-forest prediction must be calibrated and chronologically validated"]
        return result
    if not 0.5 <= probability <= 1.0:
        result["view"] = "WAIT"
        result["reasons"] = ["random-forest probability is below the directional research threshold or invalid"]
        return result
    return with_direction(result, state, prediction, "validated random-forest prediction supports the recorded direction")
