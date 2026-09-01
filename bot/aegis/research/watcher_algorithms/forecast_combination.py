"""Weighted forecast combination with uncertainty-aware directional classification."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_validated, first, number, values, with_direction

ALGORITHM_ID = "forecast_combination"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Ernest Chan — Machine Trading",
    "Yves Hilpisch — Python for Finance",
)
KEYS = ("forecast_values", "forecast_weights", "forecast_current_price", "forecast_uncertainty", "forecast_oos_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_forecast_ensemble",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    forecasts = first(state, "forecast_values")
    weights = first(state, "forecast_weights")
    current = number(first(state, "forecast_current_price", "current_price"))
    uncertainty = number(first(state, "forecast_uncertainty"))
    oos = first(state, "forecast_oos_status")
    if not isinstance(forecasts, (list, tuple)) or not isinstance(weights, (list, tuple)) or len(forecasts) != len(weights) or not forecasts:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["same_length_forecast_values_and_weights"]
        return result
    pairs = [(number(value), number(weight)) for value, weight in zip(forecasts, weights)]
    if any(value is None or weight is None for value, weight in pairs) or current is None or uncertainty is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_forecasts_current_price_and_uncertainty"]
        return result
    weight_sum = sum(weight for _, weight in pairs)
    if weight_sum <= 0 or uncertainty < 0 or not explicitly_validated(oos, accepted=("walk forward", "sealed oos", "validated")):
        result["view"] = "WAIT"
        result["reasons"] = ["forecast combination needs positive weights, uncertainty, and chronological OOS support"]
        return result
    combined = sum(value * weight for value, weight in pairs) / weight_sum
    result["combined_forecast"] = combined
    result["forecast_displacement"] = combined - current
    if combined - current > uncertainty:
        return with_direction(result, state, "BUY", "weighted forecast exceeds current price by more than uncertainty")
    if combined - current < -uncertainty:
        return with_direction(result, state, "SELL", "weighted forecast is below current price by more than uncertainty")
    result["view"] = "WAIT"
    result["reasons"] = ["combined forecast displacement is within uncertainty"]
    return result
