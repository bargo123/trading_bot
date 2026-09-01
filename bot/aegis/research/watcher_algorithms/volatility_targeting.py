"""Volatility-targeting context used for research sizing and risk diagnostics."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "volatility_targeting"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Richard Grinold and Ronald Kahn — Active Portfolio Management",
    "Michel M. Dacorogna et al. — An Introduction to High-Frequency Finance",
)
KEYS = ("target_volatility", "realized_volatility", "volatility_scalar", "volatility_target_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_volatility_target",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    target = number(first(state, "target_volatility"))
    realized = number(first(state, "realized_volatility"))
    scalar = number(first(state, "volatility_scalar"))
    if None in {target, realized, scalar} or target <= 0 or realized <= 0 or scalar <= 0 or not explicitly_validated(first(state, "volatility_target_status")):
        result["view"] = "WAIT"
        result["reasons"] = ["volatility target requires validated positive target, realized volatility, and scalar"]
        return result
    result["implied_scalar"] = target / realized
    result["scalar_consistent"] = abs(scalar - result["implied_scalar"]) <= max(0.05, 0.1 * result["implied_scalar"])
    result["view"] = "WAIT"
    result["reasons"] = ["volatility targeting controls size and does not choose BUY or SELL"]
    return result
