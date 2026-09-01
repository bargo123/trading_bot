"""Narang's order-size versus observed liquidity impact diagnostic."""
from __future__ import annotations

from ._common import absent, base, first, number, explicitly_observed, values

ALGORITHM_ID = "narang_liquidity_impact"
SOURCES = ("Rishi K Narang — Inside the Black Box",)
KEYS = (
    "narang_order_size",
    "narang_available_liquidity",
    "narang_market_impact_estimate_usd",
    "narang_liquidity_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("order_size_and_observed_liquidity",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    order_size = number(first(state, "narang_order_size"))
    liquidity = number(first(state, "narang_available_liquidity"))
    impact = number(first(state, "narang_market_impact_estimate_usd"))
    provenance = first(state, "narang_liquidity_data_provenance")
    if order_size is None or liquidity is None or impact is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_order_liquidity_and_impact"]
        return result
    if order_size <= 0 or liquidity <= 0 or impact < 0:
        result["narang_liquidity_assessment"] = "INVALID_LIQUIDITY_INPUT"
        result["reasons"] = ["order size and available liquidity must be positive and impact non-negative"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["narang_liquidity_data_provenance"]
        return result

    ratio = order_size / liquidity
    result["narang_size_to_liquidity_ratio"] = ratio
    result["narang_market_impact_estimate_usd"] = impact
    result["directional_claim"] = False
    if ratio > 1.0:
        result["narang_liquidity_assessment"] = "IMPACT_RISK"
        result["reasons"] = ["the proposed size exceeds the observed available liquidity"]
    else:
        result["narang_liquidity_assessment"] = "LIQUIDITY_COMPATIBLE"
        result["reasons"] = ["the proposed size fits within the observed available liquidity"]
    return result
