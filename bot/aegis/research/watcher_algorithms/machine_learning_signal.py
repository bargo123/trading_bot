"""Read-only ML signal perspective with artifact/calibration fail-closed gates."""
from __future__ import annotations

from ._common import base, first, number, text, values, with_direction

ALGORITHM_ID = "machine_learning_signal"
SOURCES = (
    "Advances in Financial Machine Learning — Marcos Lopez de Prado",
    "Machine Learning for Algorithmic Trading — Stefan Jansen",
    "Inside the Black Box — Rishi K. Narang",
)
KEYS = ("ml_prediction", "ml_probability", "ml_artifact_status", "ml_calibration_status", "ml_authorized_symbols", "ml_horizon_s", "ml_feature_timestamp")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("calibrated_ml_prediction",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    artifact = text(first(state, "ml_artifact_status")).upper()
    calibration = text(first(state, "ml_calibration_status")).upper()
    if artifact in {"", "SHADOW_ONLY", "SHADOW_ONLY_NO_POSITIVE_OOS", "INVALID", "MISSING"}:
        result["view"] = "WAIT"
        result["reasons"] = ["ML artifact is missing, invalid, or shadow-only"]
        return result
    if calibration not in {"CALIBRATED", "VALIDATED"}:
        result["view"] = "WAIT"
        result["reasons"] = ["ML probability is not calibrated"]
        return result
    symbol = text(first(state, "symbol"))
    authorized = first(state, "ml_authorized_symbols")
    if not isinstance(authorized, (list, tuple, set, frozenset)) or symbol not in {str(item) for item in authorized}:
        result["view"] = "WAIT"
        result["reasons"] = ["symbol is not authorized by the ML artifact"]
        return result
    prediction = text(first(state, "ml_prediction")).upper()
    probability = number(first(state, "ml_probability"))
    if prediction not in {"BUY", "SELL"} or probability is None or not 0.5 < probability <= 1.0:
        result["view"] = "WAIT"
        result["reasons"] = ["ML prediction or probability is not usable"]
        return result
    return with_direction(result, state, prediction, "calibrated authorized ML prediction is available")
