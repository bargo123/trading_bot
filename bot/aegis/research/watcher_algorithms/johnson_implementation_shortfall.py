"""Implementation-shortfall perspective from Johnson's DMA text.

This is a pre-trade cost diagnostic for the read-only Watcher.  It compares a
decision benchmark with an expected executable price and adds separately
measured cost components exactly once.  It never authorizes an order.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, side, values

ALGORITHM_ID = "johnson_implementation_shortfall"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA",)
KEYS = (
    "side",
    "johnson_decision_price",
    "johnson_expected_execution_price",
    "johnson_expected_spread_cost",
    "johnson_expected_delay_cost",
    "johnson_expected_market_impact",
    "johnson_expected_timing_risk",
    "johnson_expected_commission",
    "johnson_cost_model_status",
    "johnson_shortfall_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_shortfall_cost_model",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    decision = number(first(state, "johnson_decision_price"))
    expected_execution = number(first(state, "johnson_expected_execution_price"))
    component_keys = (
        "johnson_expected_spread_cost",
        "johnson_expected_delay_cost",
        "johnson_expected_market_impact",
        "johnson_expected_timing_risk",
        "johnson_expected_commission",
    )
    components = {key: number(first(state, key)) for key in component_keys}
    missing = [key for key, value in {"side": candidate_side, "johnson_decision_price": decision, "johnson_expected_execution_price": expected_execution, **components}.items() if value is None]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        result["reasons"] = ["implementation shortfall needs a complete executable pre-trade cost vector"]
        return result
    if decision <= 0 or expected_execution <= 0 or any(value < 0 for value in components.values()):
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["shortfall prices must be positive and cost components non-negative"]
        return result
    if not explicitly_validated(first(state, "johnson_cost_model_status")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["johnson_cost_model_status"]
        result["reasons"] = ["shortfall cost model is not explicitly validated"]
        return result
    if not explicitly_observed(first(state, "johnson_shortfall_data_provenance"), accepted=("observed", "measured", "validated")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["johnson_shortfall_data_provenance"]
        result["reasons"] = ["shortfall inputs do not have an accepted observed/model provenance"]
        return result

    price_shortfall = expected_execution - decision if candidate_side == "BUY" else decision - expected_execution
    expected_shortfall = price_shortfall + sum(components.values())
    result["johnson_price_shortfall"] = price_shortfall
    result["johnson_expected_shortfall"] = expected_shortfall
    result["johnson_shortfall_components"] = dict(components)
    result["johnson_shortfall_assessment"] = "FAVORABLE_PRICE" if expected_shortfall <= 0 else "COST_EXPOSURE"
    result["view"] = "WAIT"
    result["reasons"] = ["implementation shortfall is a cost/risk diagnostic, not a directional authority"]
    return result
