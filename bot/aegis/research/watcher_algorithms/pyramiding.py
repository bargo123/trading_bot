"""Read-only, profit-funded same-thesis pyramiding perspective.

This is a research view only.  It never creates an order and rejects any
averaging-down or loss-driven size increase.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pyramiding"
SOURCES = (
    "Robert Carver — Systematic Trading",
    "Alexander Elder — The New Trading for a Living",
    "pyramiding full text extracted",
)
KEYS = ("pyramid_state", "same_thesis", "position_profit", "pyramid_signal", "risk_increase_after_loss")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("pyramid_authorization", "same_thesis_state", "positive_position"))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_label = normalized_status(first(state, "pyramid_state"))
    same_thesis = first(state, "same_thesis") is True
    profit = number(first(state, "position_profit"))
    signal = normalized_status(first(state, "pyramid_signal"))
    loss_increase = first(state, "risk_increase_after_loss") is True
    if loss_increase or state_label in {"averaging down", "martingale", "loss recovery"}:
        result["view"] = "WAIT"
        result["reasons"] = ["loss-driven size increase is forbidden"]
        return result
    if state_label not in {"authorized", "add allowed", "confirmed"} or not same_thesis or profit is None or profit <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["pyramiding requires explicit authorization, same thesis, and positive open profit"]
        return result
    if signal not in {"buy", "sell"}:
        result["view"] = "WAIT"
        result["reasons"] = ["same-thesis add direction is unavailable"]
        return result
    result = with_direction(result, state, signal.upper(), "profit-funded same-thesis add is recorded as a research candidate")
    result["pyramid_action"] = "SHADOW_ADD_CANDIDATE"
    result["position_profit"] = profit
    return result

