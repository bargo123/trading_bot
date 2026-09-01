"""Bob Volman's Block Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_block_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_block_bars", "volman_block_compression",
    "volman_market_pressure",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "block break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not a block break"]
        return result
    signal = volman_direction(state)
    pressure = normalized_status(first(state, "volman_market_pressure"))
    if signal is None or signal != ("up" if pressure in {"up", "bull", "bullish"} else "down" if pressure in {"down", "bear", "bearish"} else None):
        result["view"] = "WAIT"
        result["reasons"] = ["block pressure does not identify a winning side"]
        return result
    bars = number(first(state, "volman_block_bars"))
    if bars is None or bars < 2 or not volman_truth(first(state, "volman_block_compression")):
        result["view"] = "WAIT"
        result["reasons"] = ["a compressed block with a defined signal line is not observed"]
        return result
    if not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["block-break trigger or path to the scalp target is not confirmed"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "compressed block broke toward the observed path of least resistance")
