"""The Ultimate Forex Trading System's weakening-M/strengthening-W study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_triangle_pattern"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_triangle_shape",
    "ultimate_triangle_leg_directions",
    "ultimate_triangle_leg_sizes",
    "ultimate_triangle_final_leg_weak",
    "ultimate_triangle_completed",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    shape = normalized_status(first(state, "ultimate_triangle_shape"))
    directions = first(state, "ultimate_triangle_leg_directions")
    sizes = first(state, "ultimate_triangle_leg_sizes")
    if not isinstance(directions, (list, tuple)) or not isinstance(sizes, (list, tuple)) or len(directions) != 3 or len(sizes) != 3:
        result["view"] = "WAIT"
        result["reasons"] = ["three causal triangle legs with directions and sizes are required"]
        return result
    directions = [normalized_status(value).upper() for value in directions]
    numeric_sizes = [number(value) for value in sizes]
    if any(value not in {"UP", "DOWN"} for value in directions) or any(value is None or value <= 0 for value in numeric_sizes):
        result["view"] = "WAIT"
        result["reasons"] = ["triangle directions and leg sizes are invalid"]
        return result
    if not _truthy(first(state, "ultimate_triangle_completed")) or not _truthy(first(state, "ultimate_triangle_final_leg_weak")):
        result["view"] = "WAIT"
        result["reasons"] = ["the triangle must be complete and its final leg explicitly weak"]
        return result
    if shape == "weakening m":
        expected = ["UP", "DOWN", "UP"]
        signal = "SELL"
    elif shape == "strengthening w":
        expected = ["DOWN", "UP", "DOWN"]
        signal = "BUY"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["triangle shape is not the source's weakening M or strengthening W"]
        return result
    if directions != expected:
        result["view"] = "WAIT"
        result["reasons"] = ["triangle leg direction sequence does not match the source shape"]
        return result
    middle_ratio = numeric_sizes[1] / numeric_sizes[0]
    if not (1 / 3 <= middle_ratio <= 1 / 2):
        result["view"] = "WAIT"
        result["reasons"] = ["the corrective middle leg is not between one-third and one-half of the first leg"]
        return result
    result["ultimate_triangle_middle_leg_ratio"] = middle_ratio
    return with_direction(result, state, signal, "the completed weakening/strengthening triangle points to its source reversal")
