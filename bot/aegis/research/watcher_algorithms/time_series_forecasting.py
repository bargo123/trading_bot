"""Forecasting perspective with explicit point-in-time OOS metadata."""
from __future__ import annotations

from ._common import base, first, number, text, values, with_direction

ALGORITHM_ID = "time_series_forecasting"
SOURCES = (
    "An Introduction to High-Frequency Finance — Dacorogna et al.",
    "Python for Finance — Yves Hilpisch",
    "Machine Trading — Ernest P. Chan",
)
KEYS = (
    "forecast_price", "forecast_current_price", "forecast_horizon_s", "forecast_model",
    "forecast_oos_status", "forecast_uncertainty", "forecast_oos_n", "forecast_mae",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("timestamped_oos_forecast",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    status = text(first(state, "forecast_oos_status")).upper()
    if status not in {"WALK_FORWARD", "SEALED_OOS", "VALIDATED"}:
        result["view"] = "WAIT"
        result["reasons"] = ["forecast is not identified as chronological out-of-sample"]
        return result
    forecast = number(first(state, "forecast_price"))
    current = number(first(state, "forecast_current_price", "mid", "entry"))
    uncertainty = number(first(state, "forecast_uncertainty"))
    oos_n = number(first(state, "forecast_oos_n"))
    mae = number(first(state, "forecast_mae"))
    if forecast is None or current is None or uncertainty is None or oos_n is None or mae is None:
        result["view"] = "MISSING_DATA"
        result["applicability"] = "MISSING_DATA"
        result["missing_inputs"] = [
            key for key, value in (
                ("forecast_price", forecast),
                ("forecast_current_price", current),
                ("forecast_uncertainty", uncertainty),
                ("forecast_oos_n", oos_n),
                ("forecast_mae", mae),
            ) if value is None
        ]
        result["reasons"] = ["forecast requires measured walk-forward error and sample size"]
        return result
    if uncertainty < 0 or mae < 0 or oos_n < 20:
        result["view"] = "WAIT"
        result["reasons"] = ["forecast walk-forward evidence has insufficient or invalid error statistics"]
        return result
    move = forecast - current
    if abs(move) <= uncertainty:
        result["view"] = "WAIT"
        result["reasons"] = ["forecast displacement is not greater than its uncertainty"]
    elif move > 0:
        return with_direction(result, state, "BUY", "validated forecast exceeds current price beyond uncertainty")
    else:
        return with_direction(result, state, "SELL", "validated forecast is below current price beyond uncertainty")
    return result
