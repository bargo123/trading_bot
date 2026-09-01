"""Meta-labeling perspective: a calibrated secondary model may accept a base signal."""
from __future__ import annotations

from ._common import absent, base, explicitly_calibrated, explicitly_validated, first, number, strings, values, with_direction

ALGORITHM_ID = "meta_labeling"
SOURCES = (
    "Marcos López de Prado — Advances in Financial Machine Learning",
    "Stefan Jansen — Machine Learning for Algorithmic Trading",
)
KEYS = ("primary_signal", "meta_probability", "meta_calibration_status", "meta_oos_status", "meta_horizon_s")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("calibrated_meta_label",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = str(first(state, "primary_signal") or "").strip().upper()
    probability = number(first(state, "meta_probability"))
    calibration = strings(state, "meta_calibration_status")
    oos = strings(state, "meta_oos_status")
    if signal not in {"BUY", "SELL"} or probability is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["primary_signal_and_meta_probability"]
        return result
    if not explicitly_calibrated(calibration) or not explicitly_validated(oos, accepted=("walk forward", "sealed oos", "validated")):
        result["view"] = "WAIT"
        result["reasons"] = ["meta-label must be calibrated and supported by chronological out-of-sample evidence"]
        return result
    if not 0.0 <= probability <= 1.0:
        result["view"] = "WAIT"
        result["reasons"] = ["meta-label probability is invalid"]
        return result
    if probability < 0.5:
        result["view"] = "WAIT"
        result["reasons"] = ["meta-label rejects the primary signal"]
        return result
    return with_direction(result, state, signal, "calibrated meta-label accepts the primary point-in-time signal")
