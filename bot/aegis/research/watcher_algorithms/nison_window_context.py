"""Nison rising/falling-window support, resistance, and close-break rules."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_window_context"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_window_direction",
    "nison_window_role",
    "nison_window_filled",
    "nison_window_age_sessions",
    "nison_window_break_close",
    "nison_window_confirmed",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_window_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["window support/resistance has not been confirmed"]
        return result
    direction = normalized_status(first(state, "nison_window_direction"))
    role = normalized_status(first(state, "nison_window_role"))
    filled = volman_truth(first(state, "nison_window_filled"))
    age = number(first(state, "nison_window_age_sessions"))
    close_break = normalized_status(first(state, "nison_window_break_close"))
    if age is None or age < 0:
        result["view"] = "WAIT"
        result["reasons"] = ["window age is invalid"]
        return result
    if direction == "rising" and role == "support":
        if close_break == "below bottom":
            result["nison_window_assessment"] = "RISING_WINDOW_SUPPORT_BROKEN"
            return with_direction(result, state, "SELL", "a closing break below rising-window support confirmed weakness")
        if not filled and age >= 3:
            result["nison_window_assessment"] = "RISING_WINDOW_CONFIRMED_SUPPORT"
            return with_direction(result, state, "BUY", "unfilled rising window remained support for three sessions")
    if direction == "falling" and role == "resistance":
        if close_break == "above top":
            result["nison_window_assessment"] = "FALLING_WINDOW_RESISTANCE_BROKEN"
            return with_direction(result, state, "BUY", "a closing break above falling-window resistance confirmed strength")
        if not filled and age >= 3:
            result["nison_window_assessment"] = "FALLING_WINDOW_CONFIRMED_RESISTANCE"
            return with_direction(result, state, "SELL", "unfilled falling window remained resistance for three sessions")
    result["view"] = "WAIT"
    result["reasons"] = ["window is filled, too young for three-session confirmation, or has invalid role/direction"]
    return result
