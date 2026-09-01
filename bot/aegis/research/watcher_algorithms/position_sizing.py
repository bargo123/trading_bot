"""Risk-budget position-size calculation kept separate from trade authority."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "position_sizing"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Alexander Elder — The New Trading for a Living",
    "Marcel Link — High Probability Trading",
)
KEYS = ("risk_budget_usd", "stop_distance", "value_per_price_unit", "sizing_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_risk_budget_geometry",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    budget = number(first(state, "risk_budget_usd"))
    stop = number(first(state, "stop_distance"))
    value = number(first(state, "value_per_price_unit"))
    if None in {budget, stop, value} or budget <= 0 or stop <= 0 or value <= 0 or not explicitly_validated(first(state, "sizing_status")):
        result["view"] = "WAIT"
        result["reasons"] = ["position sizing needs a positive validated risk budget and stop geometry"]
        return result
    result["theoretical_units"] = budget / (stop * value)
    result["view"] = "WAIT"
    result["reasons"] = ["position sizing reports risk geometry and does not authorize an order"]
    return result
