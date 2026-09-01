"""Narang's point-in-time linear alpha-forecast blending perspective."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, side, values, with_direction

ALGORITHM_ID = "narang_linear_alpha_blend"
SOURCES = ("Rishi K Narang — Inside the Black Box",)
KEYS = (
    "side",
    "narang_alpha_forecasts",
    "narang_alpha_weights",
    "narang_blend_threshold",
    "narang_blend_model_status",
    "narang_blend_data_provenance",
)


def _finite_series(value):
    if not isinstance(value, (list, tuple)) or not value:
        return None
    result = []
    for item in value:
        numeric = number(item)
        if numeric is None:
            return None
        result.append(numeric)
    return result


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "narang_blend_data_provenance"),
        accepted=("observed", "measured", "timestamped", "replay"),
    ):
        missing.append("narang_blend_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    forecasts = _finite_series(first(state, "narang_alpha_forecasts"))
    weights = _finite_series(first(state, "narang_alpha_weights"))
    threshold = number(first(state, "narang_blend_threshold"))
    if (
        candidate_side is None
        or forecasts is None
        or weights is None
        or len(forecasts) != len(weights)
        or threshold is None
        or threshold <= 0
        or not any(abs(weight) > 0 for weight in weights)
        or not all(math.isfinite(weight) for weight in weights)
    ):
        result["narang_blend_action"] = "INVALID_BLEND_INPUT"
        result["reasons"] = ["linear blending needs equally sized finite forecast/weight series and a positive threshold"]
        return result
    if not explicitly_validated(first(state, "narang_blend_model_status")):
        result["narang_blend_action"] = "MODEL_NOT_VALIDATED"
        result["reasons"] = ["a composite forecast requires a validated point-in-time blend model"]
        return result

    composite = sum(forecast * weight for forecast, weight in zip(forecasts, weights))
    result.update(
        {
            "narang_composite_forecast": composite,
            "narang_alpha_forecasts": forecasts,
            "narang_alpha_weights": weights,
            "narang_blend_threshold": threshold,
        }
    )
    if abs(composite) < threshold:
        result["narang_blend_action"] = "COMPOSITE_BELOW_THRESHOLD"
        result["reasons"] = ["the weighted composite forecast is not materially displaced"]
        return result
    signal = "BUY" if composite > 0 else "SELL"
    result["narang_blend_action"] = "COMPOSITE_FORECAST_SUPPORTS"
    return with_direction(result, state, signal, "validated linear alpha forecasts combine into a material composite")
