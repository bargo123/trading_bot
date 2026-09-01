"""Narang's transaction-cost hurdle for a proposed benefit."""
from __future__ import annotations

from ._common import absent, base, first, number, explicitly_observed, values

ALGORITHM_ID = "narang_cost_hurdle"
SOURCES = ("Rishi K Narang — Inside the Black Box",)
KEYS = (
    "narang_expected_gross_benefit_usd",
    "narang_estimated_transaction_cost_usd",
    "narang_cost_components",
    "narang_cost_data_provenance",
)
_COMPONENTS = ("commission", "slippage", "impact")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("gross_benefit_and_cost_components",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    gross = number(first(state, "narang_expected_gross_benefit_usd"))
    estimated = number(first(state, "narang_estimated_transaction_cost_usd"))
    components = first(state, "narang_cost_components")
    provenance = first(state, "narang_cost_data_provenance")
    if gross is None or estimated is None or not isinstance(components, dict):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_gross_benefit_cost_and_cost_components"]
        return result
    if gross < 0 or estimated < 0:
        result["narang_cost_assessment"] = "INVALID_COST_INPUT"
        result["reasons"] = ["gross benefit and transaction cost must be non-negative"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["narang_cost_data_provenance"]
        return result

    numeric_components = {}
    for name in _COMPONENTS:
        value = number(components.get(name))
        if value is None or value < 0:
            result["narang_cost_assessment"] = "INVALID_COST_COMPONENTS"
            result["reasons"] = ["commission, slippage, and impact must be finite non-negative observations"]
            return result
        numeric_components[name] = value
    component_total = sum(numeric_components.values())
    if abs(component_total - estimated) > 1e-9:
        result["narang_cost_assessment"] = "COST_INPUT_INCONSISTENT"
        result["narang_cost_components_total_usd"] = component_total
        result["narang_estimated_transaction_cost_usd"] = estimated
        result["reasons"] = ["the total cost estimate must equal the sum of its components"]
        return result

    result["narang_cost_components_total_usd"] = component_total
    result["narang_estimated_transaction_cost_usd"] = estimated
    result["narang_net_benefit_usd"] = gross - component_total
    result["directional_claim"] = False
    if gross <= component_total:
        result["narang_cost_assessment"] = "COST_HURDLE_NOT_CLEARED"
        result["reasons"] = ["expected gross benefit does not clear the measured all-in transaction cost"]
    else:
        result["narang_cost_assessment"] = "COST_HURDLE_CLEARED"
        result["reasons"] = ["expected gross benefit clears commission, slippage, and impact once"]
    return result
