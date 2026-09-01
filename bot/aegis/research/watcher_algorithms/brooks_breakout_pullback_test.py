"""Al Brooks' breakout-pullback and breakout-test perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "brooks_breakout_pullback_test"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_breakout_direction",
    "brooks_initial_breakout_confirmed",
    "brooks_pullback_bars",
    "brooks_pullback_reached_breakout",
    "brooks_opposite_signal",
    "brooks_follow_through_confirmed",
    "brooks_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "brooks_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("brooks_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "brooks_breakout_direction")).upper()
    bars = number(first(state, "brooks_pullback_bars"))
    if direction not in {"UP", "DOWN"} or bars is None or not 1 <= bars <= 5:
        result["view"] = "WAIT"
        result["reasons"] = ["a breakout direction and one-to-five-bar pullback are required"]
        return result
    if not _truthy(first(state, "brooks_initial_breakout_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the initial breakout has not been confirmed"]
        return result
    if not _truthy(first(state, "brooks_pullback_reached_breakout")):
        result["view"] = "WAIT"
        result["reasons"] = ["the pullback has not tested the original breakout/entry area"]
        return result
    if _truthy(first(state, "brooks_opposite_signal")):
        result["view"] = "WAIT"
        result["reasons"] = ["an opposite signal makes this a failed breakout rather than a continuation test"]
        return result
    if not _truthy(first(state, "brooks_follow_through_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["follow-through after the breakout test is not confirmed"]
        return result
    signal = "BUY" if direction == "UP" else "SELL"
    result["brooks_breakout_test_bars"] = bars
    return with_direction(result, state, signal, "the breakout pulled back to test its entry and resumed without an opposite signal")
