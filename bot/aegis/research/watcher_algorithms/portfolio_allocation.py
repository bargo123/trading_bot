"""Portfolio-impact perspective; it never turns candidate side into a signal."""
from __future__ import annotations

from ._common import base, direction, first, number, strings, values, with_direction

ALGORITHM_ID = "portfolio_allocation"
SOURCES = (
    "Active Portfolio Management — Richard Grinold and Ronald Kahn",
    "Systematic Trading — Robert Carver",
    "Quantitative Finance For Dummies — Steve Bell",
)
KEYS = ("portfolio_state", "portfolio_impact", "marginal_risk", "correlation_to_open", "portfolio_bias", "portfolio_limit")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("portfolio_impact_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = strings(state, "portfolio_state")
    impact_text = strings(state, "portfolio_impact", "correlation_to_open")
    if any(token in state_text for token in ("blocked", "outside", "excess", "high_risk")) or any(token in impact_text for token in ("excess", "high_risk", "high_correlation", "correlated")):
        result["view"] = "WAIT"
        result["reasons"] = ["portfolio impact exceeds the supplied allocation context"]
        result["allocation_assessment"] = "OUTSIDE_LIMIT"
        return result
    risk = number(first(state, "marginal_risk"))
    if risk is None:
        result["view"] = "MISSING_DATA"
        result["applicability"] = "MISSING_DATA"
        result["missing_inputs"] = ["marginal_risk"]
        result["reasons"] = ["portfolio impact lacks marginal risk"]
        return result
    result["allocation_assessment"] = "WITHIN_LIMIT"
    signal = direction(strings(state, "portfolio_bias"))
    if signal:
        return with_direction(result, state, signal, "portfolio context is within limit and has a separate directional bias")
    result["view"] = "WAIT"
    result["reasons"] = ["portfolio context is within limit but has no directional bias"]
    return result
