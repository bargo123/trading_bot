"""Carver's forecast scaling and cap as a read-only risk diagnostic."""
from __future__ import annotations

from ._common import absent, base, first, number, normalized_status, values

ALGORITHM_ID = "carver_forecast_cap"
SOURCES = ("Robert Carver — Systematic Trading",)
KEYS = (
    "carver_forecast",
    "carver_forecast_average_abs",
    "carver_forecast_cap_multiple",
    "carver_forecast_data_provenance",
)


def _observed(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in provenance for token in ("observed", "historical", "live", "broker"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _observed(first(state, "carver_forecast_data_provenance")):
        missing.append("carver_forecast_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    forecast = number(first(state, "carver_forecast"))
    average_abs = number(first(state, "carver_forecast_average_abs"))
    cap_multiple = number(first(state, "carver_forecast_cap_multiple"))
    if forecast is None or average_abs is None or cap_multiple is None or average_abs <= 0 or cap_multiple <= 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_positive_forecast_scale"]
        return result

    cap = average_abs * cap_multiple
    result.update({
        "carver_forecast_cap": cap,
        "carver_forecast_abs": abs(forecast),
        "directional_claim": False,
    })
    if abs(forecast) > cap:
        result["carver_forecast_action"] = "FORECAST_CAPPED"
        result["reasons"] = ["absolute forecast exceeds the observed cap multiple"]
    else:
        result["carver_forecast_action"] = "FORECAST_WITHIN_CAP"
        result["reasons"] = ["absolute forecast remains within the observed cap multiple"]
    return result
