"""Bob Volman's Advanced Range Break, represented as a causal quote-bar proxy."""
from __future__ import annotations

from ._common import base, first, number, normalized_status, volman_confirmed, volman_direction, volman_has_setup, volman_missing, volman_truth, with_direction

ALGORITHM_ID = "volman_advanced_range_break"
SOURCES = ("Bob Volman — Forex Price Action Scalping",)
KEYS = (
    "volman_setup", "volman_trend", "volman_signal_direction", "volman_signal_break",
    "volman_path_clear", "volman_prior_range_break", "volman_post_break_retest",
    "volman_signal_cluster_bars",
)


def evaluate(state):
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    missing = volman_missing(state, KEYS)
    if missing:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if not volman_has_setup(state, "advanced range break"):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the observed quote-bar setup is not an advanced range break"]
        return result
    if not volman_truth(first(state, "volman_prior_range_break")) or not volman_truth(first(state, "volman_post_break_retest")):
        result["view"] = "WAIT"
        result["reasons"] = ["a prior range break followed by a contained retest is not observed"]
        return result
    clusters = number(first(state, "volman_signal_cluster_bars"))
    if clusters is None or clusters < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["post-break signal cluster is too thin to confirm a retest"]
        return result
    signal = volman_direction(state)
    if signal is None or not volman_confirmed(state) or not volman_truth(first(state, "volman_path_clear")):
        result["view"] = "WAIT"
        result["reasons"] = ["advanced range-break trigger or executable path is absent"]
        return result
    return with_direction(result, state, "BUY" if signal == "up" else "SELL", "post-break retest cluster broke in the original range-break direction")
