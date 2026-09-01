"""Liquidity-seeking perspective from Johnson's DMA text."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction

ALGORITHM_ID = "johnson_liquidity_seeking"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA",)
KEYS = (
    "side",
    "johnson_favorable_depth",
    "johnson_total_depth",
    "johnson_execution_probability",
    "johnson_favorable_price",
    "johnson_depth_data_provenance",
)


def _positive_flag(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "favorable", "in_the_money", "in the money"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("observed_depth_and_execution_probability",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    favorable_depth = number(first(state, "johnson_favorable_depth"))
    total_depth = number(first(state, "johnson_total_depth"))
    execution_probability = number(first(state, "johnson_execution_probability"))
    missing = [
        key for key, value in (
            ("side", candidate_side),
            ("johnson_favorable_depth", favorable_depth),
            ("johnson_total_depth", total_depth),
            ("johnson_execution_probability", execution_probability),
            ("johnson_favorable_price", first(state, "johnson_favorable_price")),
        ) if value is None
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if favorable_depth < 0 or total_depth <= 0 or favorable_depth > total_depth or not 0 <= execution_probability <= 1:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["liquidity-seeking depth and execution probability are outside valid ranges"]
        return result
    if not explicitly_observed(first(state, "johnson_depth_data_provenance"), accepted=("observed", "measured")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["johnson_depth_data_provenance"]
        result["reasons"] = ["liquidity-seeking requires real observed order-book depth, not a quote or tick proxy"]
        return result

    depth_ratio = favorable_depth / total_depth
    result["johnson_favorable_depth_ratio"] = depth_ratio
    result["johnson_execution_probability"] = execution_probability
    if not _positive_flag(first(state, "johnson_favorable_price")):
        result["johnson_liquidity_seeking_assessment"] = "UNFAVORABLE_PRICE"
        result["view"] = "WAIT"
        result["reasons"] = ["observed depth is not at a favorable candidate price"]
        return result
    if depth_ratio >= 0.5 and execution_probability >= 0.5:
        result["johnson_liquidity_seeking_assessment"] = "FAVORABLE_DEPTH"
        return with_direction(result, state, candidate_side, "favorable observed depth and executable probability support liquidity seeking")
    result["johnson_liquidity_seeking_assessment"] = "INSUFFICIENT_EXECUTION_LIQUIDITY"
    result["view"] = "WAIT"
    result["reasons"] = ["favorable price exists but observed depth or execution probability is insufficient"]
    return result
