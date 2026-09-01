"""Realized-volatility state used as a context and risk diagnostic."""
from __future__ import annotations

from ._common import absent, base, first, number, values

ALGORITHM_ID = "realized_volatility"
SOURCES = (
    "Michel M. Dacorogna et al. — An Introduction to High-Frequency Finance",
    "Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",
)
KEYS = ("realized_volatility", "realized_volatility_window_s", "realized_volatility_observation_n", "volatility_regime")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("realized_volatility_measure",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    volatility = number(first(state, "realized_volatility"))
    window = number(first(state, "realized_volatility_window_s"))
    observations = number(first(state, "realized_volatility_observation_n"))
    if None in {volatility, window, observations} or volatility < 0 or window <= 0 or observations < 2:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_realized_volatility_observation"]
        return result
    result["volatility_assessment"] = "OBSERVED"
    result["view"] = "WAIT"
    result["reasons"] = ["realized volatility is contextual evidence, not a directional entry signal"]
    return result
