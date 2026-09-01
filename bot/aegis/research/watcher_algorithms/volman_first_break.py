"""Bob Volman's First Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_first_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_burst_move", "volman_first_pullback",
    "volman_pullback_to_ema", "volman_signal_bar_range_pips",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "first break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not a first break"]
        return result
    trend = normalized_status(first(state, "volman_trend"))
    signal = volman_direction(state)
    if trend not in {"up", "down"} or signal != trend:
        result["view"] = "WAIT"
        result["reasons"] = ["first break is not aligned with a directional trend"]
        return result
    if not all(
        volman_truth(first(state, key))
        for key in ("volman_burst_move", "volman_first_pullback", "volman_pullback_to_ema")
    ):
        result["view"] = "WAIT"
        result["reasons"] = ["burst, first pullback, and 20EMA interaction are not all observed"]
        return result
    width = number(first(state, "volman_signal_bar_range_pips"))
    if width is None or width > 7.0:
        result["view"] = "WAIT"
        result["reasons"] = ["signal bar is too wide for the observed scalp geometry"]
        return result
    if not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["first-break trigger or path to the scalp target is not confirmed"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "first pullback broke with the burst trend")
