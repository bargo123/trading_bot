"""Participation/POV execution context, never an execution authority."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values

ALGORITHM_ID = "participation_execution"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA", "Raja Velu et al. — Algorithmic Trading and Quantitative Strategies")
KEYS = ("target_participation_rate", "actual_participation_rate", "execution_side", "market_volume", "execution_volume")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("participation_execution_observation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    target = number(first(state, "target_participation_rate"))
    actual = number(first(state, "actual_participation_rate"))
    market_volume = number(first(state, "market_volume"))
    execution_volume = number(first(state, "execution_volume"))
    if None in {target, actual, market_volume, execution_volume} or not 0 < target <= 1 or market_volume <= 0 or execution_volume < 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_participation_observation"]
        return result
    result["participation_assessment"] = "UNDER_TARGET" if actual < target else "AT_OR_ABOVE_TARGET"
    result["view"] = "WAIT"
    result["reasons"] = ["participation rate is an execution schedule diagnostic, not a directional signal"]
    return result
