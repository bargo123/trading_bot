"""Walk-forward GARCH volatility forecast context."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "garch_volatility"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies", "Michel M. Dacorogna et al. — An Introduction to High-Frequency Finance")
KEYS = ("garch_forecast", "garch_model_status", "garch_observation_n", "garch_alpha", "garch_beta", "garch_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("walk_forward_garch_forecast",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    forecast = number(first(state, "garch_forecast"))
    observations = number(first(state, "garch_observation_n"))
    status = first(state, "garch_model_status")
    validated = explicitly_validated(status, accepted=("walk forward", "sealed oos", "validated"))
    if forecast is None or observations is None or forecast < 0 or observations < 100 or not validated:
        result["view"] = "WAIT"
        result["reasons"] = ["GARCH forecast must have sufficient chronological validation"]
        return result
    result["volatility_forecast"] = forecast
    result["view"] = "WAIT"
    result["reasons"] = ["GARCH forecasts volatility and does not determine trade direction"]
    return result
