"""Bob Volman's Range Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_range_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_range_bars", "volman_range_width_pips",
    "volman_prebreak_tension",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "range break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not a range break"]
        return result
    bars = number(first(state, "volman_range_bars"))
    width = number(first(state, "volman_range_width_pips"))
    signal = volman_direction(state)
    if bars is None or bars < 4 or width is None or width < 10.0:
        result["view"] = "WAIT"
        result["reasons"] = ["range is not sufficiently established for a scalp break"]
        return result
    if not volman_truth(first(state, "volman_prebreak_tension")):
        result["view"] = "WAIT"
        result["reasons"] = ["pre-breakout tension is not observed"]
        return result
    if signal is None or not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["range-break confirmation or executable path is absent"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "established range broke after observed pre-breakout tension")
