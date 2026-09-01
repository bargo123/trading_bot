"""Classic Turtle 20-day entry / 10-day exit breakout perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, number, strings, values, with_direction

ALGORITHM_ID = "turtle_breakout"
SOURCES = ("Robert Carver — Systematic Trading", "John J. Murphy — Technical Analysis of the Financial Markets")
KEYS = ("turtle_entry_lookback", "turtle_exit_lookback", "turtle_high", "turtle_low", "current_price", "turtle_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("turtle_channel_and_confirmation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    entry_n = number(first(state, "turtle_entry_lookback"))
    exit_n = number(first(state, "turtle_exit_lookback"))
    high = number(first(state, "turtle_high"))
    low = number(first(state, "turtle_low"))
    current = number(first(state, "current_price", "mid"))
    confirmed = explicitly_confirmed(first(state, "turtle_confirmation"))
    if entry_n != 20 or exit_n != 10:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "WAIT"
        result["reasons"] = ["classic Turtle entry/exit windows are 20 and 10 periods"]
        return result
    if None in {high, low, current} or low >= high or not confirmed:
        result["view"] = "WAIT"
        result["reasons"] = ["Turtle breakout requires valid channel geometry and confirmation"]
        return result
    if current > high:
        return with_direction(result, state, "BUY", "price broke the 20-period Turtle entry high")
    if current < low:
        return with_direction(result, state, "SELL", "price broke the 20-period Turtle entry low")
    result["view"] = "WAIT"
    result["reasons"] = ["price remains inside the Turtle entry channel"]
    return result
