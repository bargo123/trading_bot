"""Evidence-based shadow trade-management perspective.

This module evaluates a copied state for research only. It does not call the
production TradeController and cannot authorize, modify, or close a position.
"""
from __future__ import annotations

from ._common import absent, base, first, number, side, values, with_direction

ALGORITHM_ID = "trade_management"
SOURCES = (
    "Alexander Elder — The New Trading for a Living",
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Robert Carver — Systematic Trading",
)
KEYS = ("remaining_ev", "entry_ev", "continuation_probability", "expected_additional_upside", "expected_downside", "current_prediction_support", "mfe", "mae", "profit_floor", "exit_action", "lifecycle_state")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("trade_management_evidence",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    action = str(first(state, "exit_action") or "").lower()
    remaining_ev = number(first(state, "remaining_ev"))
    continuation = number(first(state, "continuation_probability"))
    upside = number(first(state, "expected_additional_upside"))
    downside = number(first(state, "expected_downside"))
    if action in {"abort", "scratch", "harvest", "close"} or (remaining_ev is not None and remaining_ev <= 0):
        result["management_action"] = action.upper() if action else "EXIT"
        result["why_continuing"] = "Continuing is not better: the copied exit evidence requests an exit or remaining EV is non-positive."
        result["view"] = "WAIT"
        result["reasons"] = ["management evidence says continuation is no longer preferable"]
        return result
    if continuation is not None and upside is not None and downside is not None and continuation * upside > (1.0 - continuation) * downside:
        result["management_action"] = "HOLD"
        result["why_continuing"] = "Continuation is better because continuation-weighted upside exceeds continuation-weighted downside."
        return with_direction(result, state, side(state), "continuation has positive remaining expectation in the copied evidence")
    if remaining_ev is not None and remaining_ev > 0 and side(state):
        result["management_action"] = "HOLD"
        result["why_continuing"] = "Continuation is better because remaining EV is positive and no collapse is recorded."
        return with_direction(result, state, side(state), "remaining EV is positive and no collapse is recorded")
    result["management_action"] = "WAIT"
    result["why_continuing"] = "No evidence shows that continuing is better than harvesting or exiting."
    result["view"] = "WAIT"
    result["reasons"] = ["management evidence is insufficient to justify continuation"]
    return result
