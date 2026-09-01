"""Stochastic-volatility forecast context."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "stochastic_volatility"
SOURCES = ("Yves Hilpisch — Python for Finance", "Raja Velu et al. — Algorithmic Trading and Quantitative Strategies")
KEYS = (
    "stochastic_volatility_forecast", "stochastic_volatility_status",
    "stochastic_volatility_observation_n", "stochastic_volatility_persistence",
    "stochastic_volatility_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_stochastic_volatility_forecast",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    forecast = number(first(state, "stochastic_volatility_forecast"))
    observations = number(first(state, "stochastic_volatility_observation_n"))
    status = first(state, "stochastic_volatility_status")
    validated = explicitly_validated(status, accepted=("walk forward", "sealed oos", "validated"))
    if forecast is None or observations is None or forecast < 0 or observations < 100 or not validated:
        result["view"] = "WAIT"
        result["reasons"] = ["stochastic-volatility forecast lacks sufficient chronological validation"]
        return result
    result["volatility_forecast"] = forecast
    result["view"] = "WAIT"
    result["reasons"] = ["stochastic volatility is context for risk and does not choose a direction"]
    return result
