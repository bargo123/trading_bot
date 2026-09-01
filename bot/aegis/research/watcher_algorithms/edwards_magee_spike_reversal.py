"""Edwards--Magee spike reversal study with required later-bar evidence."""
from __future__ import annotations

from ._common import base, em_missing, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "edwards_magee_spike_reversal"
SOURCES = ("Edwards & Magee — Technical Analysis of Stock Trends",)
KEYS = (
    "em_spike_context",
    "em_spike_range_ratio",
    "em_spike_close_bias",
    "em_spike_followup",
    "em_spike_confirmation",
    "em_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = em_missing(state, KEYS)
    if missing:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    context = normalized_status(first(state, "em_spike_context"))
    close_bias = normalized_status(first(state, "em_spike_close_bias"))
    range_ratio = number(first(state, "em_spike_range_ratio"))
    followup = normalized_status(first(state, "em_spike_followup"))
    if context not in {"top", "bottom"} or close_bias not in {"up", "down"} or range_ratio is None or range_ratio < 2.0:
        result["edwards_magee_assessment"] = "INVALID_SPIKE_INPUT"
        result["reasons"] = ["a spike requires an observed top/bottom context and an unusually wide range"]
        return result
    expected_bias = "down" if context == "top" else "up"
    if close_bias != expected_bias:
        result["edwards_magee_assessment"] = "SPIKE_CLOSE_DOES_NOT_REVERSE"
        result["reasons"] = ["the spike close does not identify the opposing side as the eventual winner"]
        return result
    if followup != "reversal confirmed":
        result["edwards_magee_assessment"] = "SPIKE_FOLLOWUP_UNRESOLVED"
        result["reasons"] = ["later-bar follow-up must distinguish a spike reversal from a runaway day"]
        return result
    if not explicitly_confirmed(first(state, "em_spike_confirmation")):
        result["edwards_magee_assessment"] = "SPIKE_UNCONFIRMED"
        result["reasons"] = ["the spike reversal is not explicitly confirmed"]
        return result
    signal = "SELL" if context == "top" else "BUY"
    result["edwards_magee_assessment"] = "SPIKE_REVERSAL"
    return with_direction(result, state, signal, "an unusually wide spike closed against the prior move and later bars confirmed reversal")
