"""Bob Volman's Double Doji Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_double_doji_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_pullback_to_ema", "volman_pattern_bars",
    "volman_signal_bar_range_pips",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "double doji break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not a double doji break"]
        return result
    trend = normalized_status(first(state, "volman_trend"))
    signal = volman_direction(state)
    if trend not in {"up", "down"} or signal != trend:
        result["view"] = "WAIT"
        result["reasons"] = ["double doji break is not aligned with the prevailing trend"]
        return result
    bars = number(first(state, "volman_pattern_bars"))
    width = number(first(state, "volman_signal_bar_range_pips"))
    if not volman_truth(first(state, "volman_pullback_to_ema")) or bars is None or bars < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["double doji compression at the 20EMA is not confirmed"]
        return result
    if width is None or width > 7.0:
        result["view"] = "WAIT"
        result["reasons"] = ["signal bar is too wide for the observed scalp geometry"]
        return result
    if not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["the signal break or path to the scalp target is not confirmed"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "compressed double-doji pullback broke with-trend")
