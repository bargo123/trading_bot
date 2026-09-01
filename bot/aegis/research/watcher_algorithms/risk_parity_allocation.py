"""Risk-parity portfolio context; it never manufactures a symbol direction."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, strings, values

ALGORITHM_ID = "risk_parity_allocation"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Richard Grinold and Ronald Kahn — Active Portfolio Management",
)
KEYS = ("risk_parity_weights", "risk_parity_covariance_status", "risk_parity_budget_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_risk_parity_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    weights = first(state, "risk_parity_weights")
    covariance = strings(state, "risk_parity_covariance_status")
    budget = strings(state, "risk_parity_budget_status")
    if not isinstance(weights, dict) or not weights or not explicitly_validated(covariance):
        result["view"] = "WAIT"
        result["reasons"] = ["risk-parity weights and validated covariance are required"]
        return result
    try:
        total = sum(float(value) for value in weights.values())
    except (TypeError, ValueError):
        total = -1.0
    if total <= 0 or total > 1.01 or "within" not in budget:
        result["view"] = "WAIT"
        result["reasons"] = ["risk-parity budget is not within the recorded allocation limit"]
        return result
    result["allocation_assessment"] = "RISK_PARITY_WITHIN_LIMIT"
    result["view"] = "WAIT"
    result["reasons"] = ["allocation context does not choose BUY or SELL"]
    return result
