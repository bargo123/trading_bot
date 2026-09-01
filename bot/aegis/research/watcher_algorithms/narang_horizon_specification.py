"""Narang's forecast-target and time-horizon identity check."""
from __future__ import annotations

from ._common import absent, base, first, number, explicitly_observed, values

ALGORITHM_ID = "narang_horizon_specification"
SOURCES = ("Rishi K Narang — Inside the Black Box",)
KEYS = (
    "narang_forecast_target",
    "narang_forecast_horizon_s",
    "narang_evaluation_horizon_s",
    "narang_horizon_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("forecast_target_and_exact_horizon",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    target = first(state, "narang_forecast_target")
    forecast_horizon = number(first(state, "narang_forecast_horizon_s"))
    evaluation_horizon = number(first(state, "narang_evaluation_horizon_s"))
    provenance = first(state, "narang_horizon_data_provenance")
    if not target or forecast_horizon is None or evaluation_horizon is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = [
            key
            for key, value in (
                ("narang_forecast_target", target),
                ("narang_forecast_horizon_s", forecast_horizon),
                ("narang_evaluation_horizon_s", evaluation_horizon),
            )
            if value is None or value == ""
        ]
        return result
    if forecast_horizon <= 0 or evaluation_horizon <= 0:
        result["narang_horizon_assessment"] = "INVALID_HORIZON"
        result["reasons"] = ["forecast and evaluation horizons must be positive"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["narang_horizon_data_provenance"]
        return result

    result["narang_forecast_target"] = str(target)
    result["narang_forecast_horizon_s"] = forecast_horizon
    result["narang_evaluation_horizon_s"] = evaluation_horizon
    result["narang_horizon_s"] = forecast_horizon
    if forecast_horizon != evaluation_horizon:
        result["narang_horizon_assessment"] = "HORIZON_MISMATCH"
        result["reasons"] = ["the forecast horizon does not match the outcome-evaluation horizon"]
    else:
        result["narang_horizon_assessment"] = "HORIZON_ALIGNED"
        result["reasons"] = ["forecast target and measured evaluation use the same explicit horizon"]
    result["directional_claim"] = False
    return result
