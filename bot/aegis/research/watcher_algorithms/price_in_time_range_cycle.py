"""Price-in-Time natural range-cycle context."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "price_in_time_range_cycle"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "side",
    "pit_current_ntz_width_pips",
    "pit_previous_ntz_width_pips",
    "pit_range_cycle_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("current_and_previous_ntz_ranges",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    current = number(first(state, "pit_current_ntz_width_pips"))
    previous = number(first(state, "pit_previous_ntz_width_pips"))
    if current is None or previous is None or current <= 0 or previous <= 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["positive_current_and_previous_ntz_width"]
        return result
    if not explicitly_observed(first(state, "pit_range_cycle_data_provenance"), accepted=("observed", "measured")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["pit_range_cycle_data_provenance"]
        return result
    result["pit_range_width_change_ratio"] = current / previous
    if current < previous:
        result["pit_range_cycle_assessment"] = "CONTRACTION_EXPECTED"
    elif current > previous:
        result["pit_range_cycle_assessment"] = "EXPANSION_EXPECTED"
    else:
        result["pit_range_cycle_assessment"] = "UNCHANGED_RANGE"
    result["view"] = "WAIT"
    result["reasons"] = ["range-cycle state is a regime/context diagnostic and not a standalone directional signal"]
    return result
