"""VWAP execution benchmark context, not an order sender."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values

ALGORITHM_ID = "vwap_execution"
SOURCES = (
    "Barry Johnson — Algorithmic Trading and DMA",
    "Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",
)
KEYS = ("vwap_reference", "execution_average_price", "execution_side", "execution_volume", "vwap_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("vwap_execution_benchmark",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    reference = number(first(state, "vwap_reference"))
    average = number(first(state, "execution_average_price"))
    volume = number(first(state, "execution_volume"))
    side = strings(state, "execution_side")
    if None in {reference, average, volume} or volume <= 0 or side not in {"buy", "sell"}:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_vwap_execution_observation"]
        return result
    result["benchmark_result"] = "BEAT" if (average <= reference if side == "buy" else average >= reference) else "SLIPPED"
    result["view"] = "WAIT"
    result["reasons"] = ["VWAP is an execution benchmark and cannot authorize a Watcher trade"]
    return result
