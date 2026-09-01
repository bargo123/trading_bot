"""Pole's staged spread-entry rule (research-only)."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction


ALGORITHM_ID = "pole_staged_spread_entries"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "side",
    "pole_staged_displacement",
    "pole_staged_direction",
    "pole_staged_first_entry",
    "pole_staged_next_entry",
    "pole_staged_entry_capacity",
    "pole_staged_existing_entries",
    "pole_staged_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_staged_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("pole_staged_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in values(state, *KEYS)])
    displacement = number(first(state, "pole_staged_displacement"))
    first_entry = number(first(state, "pole_staged_first_entry"))
    next_entry = number(first(state, "pole_staged_next_entry"))
    capacity = number(first(state, "pole_staged_entry_capacity"))
    existing = number(first(state, "pole_staged_existing_entries"))
    direction = normalized_status(first(state, "pole_staged_direction")).replace(" ", "_")
    candidate_side = side(state)
    if direction not in {"upper", "lower"}:
        result["pole_staged_action"] = "INVALID_DIRECTION"
        result["reasons"] = ["staged spread direction must be upper or lower"]
        return result
    if (
        any(value is None for value in (displacement, first_entry, next_entry, capacity, existing))
        or displacement < 0.0
        or first_entry <= 0.0
        or next_entry <= 0.0
        or next_entry < first_entry
        or capacity <= 0.0
        or int(capacity) != capacity
        or existing < 0.0
        or int(existing) != existing
        or existing > capacity
    ):
        result["pole_staged_action"] = "INVALID_STAGED_INPUT"
        result["reasons"] = ["staged entries need non-negative displacement and ordered positive levels"]
        return result

    capacity = int(capacity)
    existing = int(existing)
    result.update(
        {
            "pole_staged_displacement": displacement,
            "pole_staged_required_displacement": first_entry if existing == 0 else next_entry,
            "pole_staged_entry_capacity": capacity,
            "pole_staged_existing_entries": existing,
            "pole_staged_exit_policy": "SEPARATE_REVERSION_RULE",
        }
    )
    if existing >= capacity:
        result["pole_staged_action"] = "CAPACITY_REACHED"
        result["reasons"] = ["the explicit staged-entry capacity has already been reached"]
        return result

    required = result["pole_staged_required_displacement"]
    if displacement < required:
        result["pole_staged_action"] = "WAIT_FOR_NEXT_STAGED_LEVEL"
        result["reasons"] = ["spread displacement has not reached the next explicit staged-entry level"]
        return result

    if direction == "upper":
        signal = "SELL"
        result["pole_staged_action"] = "ENTER_FIRST_SHORT_SPREAD" if existing == 0 else "ADD_STAGED_SHORT_SPREAD"
    else:
        signal = "BUY"
        result["pole_staged_action"] = "ENTER_FIRST_LONG_SPREAD" if existing == 0 else "ADD_STAGED_LONG_SPREAD"
    if candidate_side != signal:
        result["pole_staged_action"] = "DIRECTION_SIDE_MISMATCH"
        result["reasons"] = ["candidate side does not match the observed upper/lower spread displacement"]
        return result
    result["pole_staged_entries_after_signal"] = existing + 1
    return with_direction(
        result,
        state,
        signal,
        "explicit spread displacement reached the source's next staged entry level",
    )

