"""Clenow's explicit 50-day extreme or trend-reversal exit study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, side, values

ALGORITHM_ID = "clenow_core_exit"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = ("side", "clenow_exit_trigger", "clenow_exit_trend_state", "clenow_exit_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    candidate_side = side(state)
    missing = []
    if candidate_side is None:
        missing.append("side")
    if first(state, "clenow_exit_trigger") is None:
        missing.append("clenow_exit_trigger")
    if first(state, "clenow_exit_trend_state") is None:
        missing.append("clenow_exit_trend_state")
    if not explicitly_observed(first(state, "clenow_exit_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("clenow_exit_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    trigger = normalized_status(first(state, "clenow_exit_trigger"))
    trend = normalized_status(first(state, "clenow_exit_trend_state"))
    if trigger not in {"50 day low", "50 day high", "none"} or trend not in {"bullish", "bearish", "range"}:
        result["clenow_exit_action"] = "WAIT_INVALID_EXIT_INPUT"
        result["reasons"] = ["the source exit requires a recognized 50-day extreme and trend state"]
        return result
    if candidate_side == "BUY" and (trigger == "50 day low" or trend == "bearish"):
        result["clenow_exit_action"] = "EXIT_LONG"
        result["reasons"] = ["long position reached the 50-day low or the 50/100 EMA trend turned bearish"]
        return result
    if candidate_side == "SELL" and (trigger == "50 day high" or trend == "bullish"):
        result["clenow_exit_action"] = "EXIT_SHORT"
        result["reasons"] = ["short position reached the 50-day high or the 50/100 EMA trend turned bullish"]
        return result
    result["clenow_exit_action"] = "HOLD_SOURCE_TREND"
    result["reasons"] = ["the source exit trigger is not reached for this position side"]
    return result
