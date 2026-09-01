"""Adaptive-shortfall price adaptation perspective from Johnson's DMA text."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "johnson_adaptive_shortfall"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA",)
KEYS = (
    "side",
    "johnson_benchmark_price",
    "johnson_current_mid",
    "johnson_adaptation_type",
    "johnson_adaptive_price_provenance",
)


def _adaptation(value):
    label = normalized_status(value)
    if label in {"aim", "aggressive in the money", "aggressive in the money aim"} or "aggressive in the money" in label:
        return "AIM"
    if label in {"pim", "passive in the money", "passive in the money pim"} or "passive in the money" in label:
        return "PIM"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("benchmark_current_price_adaptation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    benchmark = number(first(state, "johnson_benchmark_price"))
    current = number(first(state, "johnson_current_mid"))
    adaptation = _adaptation(first(state, "johnson_adaptation_type"))
    missing = [
        key for key, value in (
            ("side", candidate_side),
            ("johnson_benchmark_price", benchmark),
            ("johnson_current_mid", current),
            ("johnson_adaptation_type", adaptation),
        ) if value is None
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if benchmark <= 0 or current <= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["adaptive-shortfall prices must be positive"]
        return result
    if not explicitly_observed(first(state, "johnson_adaptive_price_provenance"), accepted=("observed", "measured")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["johnson_adaptive_price_provenance"]
        result["reasons"] = ["adaptive price comparison lacks observed quote provenance"]
        return result

    moneyness = (benchmark - current) / abs(benchmark) if candidate_side == "BUY" else (current - benchmark) / abs(benchmark)
    favorable = moneyness > 0
    result["johnson_price_moneyness"] = moneyness
    result["johnson_adaptation"] = adaptation
    if adaptation == "AIM" and favorable:
        result["johnson_adaptive_shortfall_assessment"] = "FAVORABLE_AIM"
        return with_direction(result, state, candidate_side, "aggressive-in-the-money adaptation favors the candidate at a favorable benchmark price")
    if adaptation == "PIM" and not favorable:
        result["johnson_adaptive_shortfall_assessment"] = "ADVERSE_PIM_URGENCY"
        return with_direction(result, state, candidate_side, "passive-in-the-money adaptation becomes urgent when the candidate price is adverse")
    result["johnson_adaptive_shortfall_assessment"] = "FAVORABLE_PIM_PASSIVITY" if favorable else "ADVERSE_AIM_WAIT"
    result["view"] = "WAIT"
    result["reasons"] = ["adaptive-shortfall mode does not call for aggressive participation in this price state"]
    return result
