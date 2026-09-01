"""TWAP schedule context, kept research-only."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values

ALGORITHM_ID = "twap_execution"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA", "Raja Velu et al. — Algorithmic Trading and Quantitative Strategies")
KEYS = ("twap_reference", "execution_average_price", "execution_side", "schedule_elapsed_fraction", "schedule_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("twap_schedule_observation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    reference = number(first(state, "twap_reference"))
    average = number(first(state, "execution_average_price"))
    elapsed = number(first(state, "schedule_elapsed_fraction"))
    side = strings(state, "execution_side")
    if None in {reference, average, elapsed} or side not in {"buy", "sell"} or not 0 <= elapsed <= 1:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_twap_schedule_observation"]
        return result
    schedule_status = strings(state, "schedule_status")
    result["schedule_assessment"] = "ACTIVE" if "inactive" not in schedule_status and "not active" not in schedule_status and "active" in schedule_status else "OBSERVED"
    result["view"] = "WAIT"
    result["reasons"] = ["TWAP schedule context cannot choose a directional Watcher trade"]
    return result
