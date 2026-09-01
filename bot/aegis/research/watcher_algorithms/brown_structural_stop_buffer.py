"""Brown's structural stop placement with a buffer beyond the recent extreme."""
from __future__ import annotations

from ._common import absent, base, first, number, explicitly_observed, side, values

ALGORITHM_ID = "brown_structural_stop_buffer"
SOURCES = ("Jim Brown — Profitable Forex Trading Using High and Low Risk Strategies",)
KEYS = (
    "brown_entry_price",
    "brown_recent_structural_low",
    "brown_recent_structural_high",
    "brown_stop_price",
    "brown_stop_buffer",
    "brown_stop_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("entry_extreme_stop_and_buffer",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    entry = number(first(state, "brown_entry_price"))
    low = number(first(state, "brown_recent_structural_low"))
    high = number(first(state, "brown_recent_structural_high"))
    stop = number(first(state, "brown_stop_price"))
    buffer = number(first(state, "brown_stop_buffer"))
    provenance = first(state, "brown_stop_data_provenance")
    direction = side(state)
    if any(value is None for value in (entry, low, high, stop, buffer)) or direction is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["side_entry_recent_extremes_stop_and_buffer"]
        return result
    if buffer <= 0 or not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "structure")):
        result["view"] = "MISSING_DATA" if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "structure")) else "WAIT"
        result["missing_inputs"] = ["brown_stop_data_provenance"] if result["view"] == "MISSING_DATA" else []
        result["brown_stop_assessment"] = "INVALID_BUFFER" if buffer <= 0 else "MISSING_PROVENANCE"
        return result

    if direction == "BUY":
        clearance = low - stop
        structurally_valid = stop < low and stop < entry
    else:
        clearance = stop - high
        structurally_valid = stop > high and stop > entry
    result["brown_stop_distance"] = abs(entry - stop)
    result["brown_structural_clearance"] = clearance
    result["directional_claim"] = False
    if not structurally_valid or clearance + 1e-12 < buffer:
        result["brown_stop_assessment"] = "BUFFER_INSUFFICIENT"
        result["reasons"] = ["the stop is not beyond the recent structural extreme by the observed buffer"]
        return result

    result["brown_stop_assessment"] = "STRUCTURAL_BUFFER_VALID"
    result["reasons"] = ["the stop leaves structural room while preserving the observed placement relationship"]
    return result
