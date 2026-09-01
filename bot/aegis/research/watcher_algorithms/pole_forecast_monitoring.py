"""Andrew Pole's forecast-error monitoring and intervention perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "pole_forecast_monitoring"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_forecast_value",
    "pole_observed_value",
    "pole_forecast_error_scale",
    "pole_monitoring_threshold",
    "pole_forecast_residual_streak",
    "pole_required_residual_streak",
    "pole_forecast_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_forecast_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("pole_forecast_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    forecast = number(first(state, "pole_forecast_value"))
    observed = number(first(state, "pole_observed_value"))
    error_scale = number(first(state, "pole_forecast_error_scale"))
    threshold = number(first(state, "pole_monitoring_threshold"))
    residual_streak = number(first(state, "pole_forecast_residual_streak"))
    required_streak = number(first(state, "pole_required_residual_streak"))
    if any(
        value is None
        for value in (forecast, observed, error_scale, threshold, residual_streak, required_streak)
    ) or error_scale <= 0 or threshold <= 0 or residual_streak < 0 or required_streak <= 0:
        result["pole_forecast_monitoring_action"] = "INVALID_FORECAST_INPUT"
        result["directional_claim"] = False
        result["reasons"] = ["forecast monitoring needs finite positive scale and streak thresholds"]
        return result

    residual = (observed - forecast) / error_scale
    result.update(
        {
            "pole_standardized_residual": residual,
            "pole_forecast_residual_streak": residual_streak,
            "pole_required_residual_streak": required_streak,
            "directional_claim": False,
        }
    )
    if abs(residual) < threshold:
        result["pole_forecast_monitoring_action"] = "WITHIN_MONITORING_BAND"
        result["reasons"] = ["observed outcome remains inside the forecast monitoring band"]
    elif residual_streak < required_streak:
        result["pole_forecast_monitoring_action"] = "MONITOR_RESIDUAL"
        result["reasons"] = ["forecast error exceeded its band but has not persisted for intervention"]
    else:
        result["pole_forecast_monitoring_action"] = "INTERVENE_MODEL_OR_EXIT"
        result["reasons"] = ["persistent forecast-outcome discrepancy can invalidate the model assumption"]
    return result
