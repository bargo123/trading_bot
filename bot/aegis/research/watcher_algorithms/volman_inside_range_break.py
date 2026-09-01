"""Bob Volman's Inside Range Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_inside_range_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_range_bars", "volman_inner_block_bars",
    "volman_range_room_pips",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "inside range break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not an inside range break"]
        return result
    range_bars = number(first(state, "volman_range_bars"))
    block_bars = number(first(state, "volman_inner_block_bars"))
    room = number(first(state, "volman_range_room_pips"))
    if range_bars is None or range_bars < 4 or block_bars is None or block_bars < 2 or room is None or room < 10.0:
        result["view"] = "WAIT"
        result["reasons"] = ["inside-range block or room toward the target is insufficient"]
        return result
    signal = volman_direction(state)
    if signal is None or not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["inside-range signal break or executable path is absent"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "compressed inner range broke with room inside the larger range")
