"""Fractionally differentiated feature readiness, kept separate from labels."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "fractional_differentiation"
SOURCES = (
    "Marcos López de Prado — Advances in Financial Machine Learning",
    "Yves Hilpisch — Python for Finance",
)
KEYS = (
    "fractional_diff_value", "fractional_diff_d", "fractional_diff_stationarity",
    "fractional_diff_observation_n", "fractional_diff_variance_ratio",
    "fractional_diff_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("stationary_fractionally_differentiated_feature",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    d = number(first(state, "fractional_diff_d"))
    observations = number(first(state, "fractional_diff_observation_n"))
    stationary = first(state, "fractional_diff_stationarity")
    validated_stationarity = explicitly_validated(stationary, accepted=("validated", "stationary"))
    if d is None or observations is None or not validated_stationarity:
        result["view"] = "WAIT"
        result["reasons"] = ["fractionally differentiated feature is not validated as stationary"]
        return result
    if not 0.0 <= d <= 1.0 or observations < 50:
        result["view"] = "WAIT"
        result["reasons"] = ["d or the feature sample is outside the supported research range"]
        return result
    result["feature_assessment"] = "STATIONARY_FEATURE_READY"
    result["view"] = "WAIT"
    result["reasons"] = ["feature readiness does not create a directional signal"]
    return result
