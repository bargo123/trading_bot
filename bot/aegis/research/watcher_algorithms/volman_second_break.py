"""Bob Volman's Second Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_second_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_first_break_failed", "volman_second_attempt",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "second break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not a second break"]
        return result
    trend = normalized_status(first(state, "volman_trend"))
    signal = volman_direction(state)
    if trend not in {"up", "down"} or signal != trend:
        result["view"] = "WAIT"
        result["reasons"] = ["second break is not aligned with the prevailing trend"]
        return result
    if not volman_truth(first(state, "volman_first_break_failed")) or not volman_truth(first(state, "volman_second_attempt")):
        result["view"] = "WAIT"
        result["reasons"] = ["the first failed attempt and distinct second attack are not both observed"]
        return result
    if not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["second-break trigger or path to the scalp target is not confirmed"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "second failed countertrend attempt broke with-trend")
