"""Market-profile initial-balance break and initiative perspective."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "initial_balance_profile"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
)
KEYS = ("initial_balance_high", "initial_balance_low", "current_price", "profile_state", "initial_balance_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("completed_initial_balance",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    high = number(first(state, "initial_balance_high"))
    low = number(first(state, "initial_balance_low"))
    current = number(first(state, "current_price", "mid"))
    profile = strings(state, "profile_state", "initial_balance_status")
    if None in {high, low, current} or low >= high:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_initial_balance_geometry"]
        return result
    if not any(token in profile for token in ("initiative", "breakout", "drive")):
        result["view"] = "WAIT"
        result["reasons"] = ["initial balance is present without an initiative or breakout classification"]
        return result
    if current > high and any(token in profile for token in ("up", "bull")):
        return with_direction(result, state, "BUY", "price is above the completed initial balance in an upside initiative state")
    if current < low and any(token in profile for token in ("down", "bear")):
        return with_direction(result, state, "SELL", "price is below the completed initial balance in a downside initiative state")
    result["view"] = "WAIT"
    result["reasons"] = ["price and initial-balance initiative direction do not align"]
    return result
