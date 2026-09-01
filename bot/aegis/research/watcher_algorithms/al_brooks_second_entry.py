"""Al Brooks second-entry pullback perspective."""
from __future__ import annotations

from ._common import absent, base, direction, explicitly_confirmed, first, number, strings, values, with_direction

ALGORITHM_ID = "al_brooks_second_entry"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = ("second_entry_direction", "second_entry_number", "second_entry_context", "second_entry_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_second_entry",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    entry_number = number(first(state, "second_entry_number"))
    signal = direction(first(state, "second_entry_direction"))
    context = strings(state, "second_entry_context")
    confirmed = explicitly_confirmed(first(state, "second_entry_confirmation"))
    if entry_number != 2 or signal is None or not confirmed:
        result["view"] = "WAIT"
        result["reasons"] = ["the supported Brooks setup is a confirmed second entry"]
        return result
    if signal == "BUY" and not any(token in context for token in ("bull", "up", "pullback")):
        result["view"] = "WAIT"
        result["reasons"] = ["second-entry buy lacks a bullish pullback context"]
        return result
    if signal == "SELL" and not any(token in context for token in ("bear", "down", "pullback")):
        result["view"] = "WAIT"
        result["reasons"] = ["second-entry sell lacks a bearish pullback context"]
        return result
    return with_direction(result, state, signal, "confirmed second-entry pullback pattern is recorded")
