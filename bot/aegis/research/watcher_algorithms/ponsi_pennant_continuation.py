"""Ponsi flagpole plus contracting pennant continuation perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, ponsi_missing, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_pennant_continuation"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_pattern",
    "ponsi_flagpole_direction",
    "ponsi_flagpole_impulse",
    "ponsi_consolidation_contracting",
    "ponsi_consolidation_bars",
    "ponsi_breakout_direction",
    "ponsi_breakout_confirmation",
    "ponsi_data_provenance",
)


def evaluate(state):
    missing = ponsi_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = normalized_status(first(state, "ponsi_pattern"))
    flagpole = normalized_status(first(state, "ponsi_flagpole_direction"))
    breakout = normalized_status(first(state, "ponsi_breakout_direction"))
    bars = number(first(state, "ponsi_consolidation_bars"))
    if pattern not in {"pennant", "flag", "flag continuation"} or not volman_truth(first(state, "ponsi_flagpole_impulse")):
        result["view"] = "WAIT"
        result["reasons"] = ["continuation pattern needs a sharp directional flagpole"]
        return result
    if not volman_truth(first(state, "ponsi_consolidation_contracting")) or bars is None or bars < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["continuation pause is not a measured contracting consolidation"]
        return result
    if not volman_truth(first(state, "ponsi_breakout_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["pennant or flag has not confirmed its breakout"]
        return result
    if flagpole == "up" and breakout == "up":
        return with_direction(result, state, "BUY", "sharp upside flagpole, contracting pause, and upside break agree")
    if flagpole == "down" and breakout == "down":
        return with_direction(result, state, "SELL", "sharp downside flagpole, contracting pause, and downside break agree")
    result["view"] = "WAIT"
    result["reasons"] = ["continuation breakout does not agree with the flagpole direction"]
    return result
