"""Failed-failure continuation/reversal perspective from Al Brooks."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, values, with_direction

ALGORITHM_ID = "al_brooks_failed_failure"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "failed_failure_direction",
    "initial_breakout_failed",
    "failure_of_failure",
    "failed_failure_confirmation",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_failure_of_failure",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = str(first(state, "failed_failure_direction") or "").strip().upper()
    if signal not in {"BUY", "SELL"} or first(state, "initial_breakout_failed") is not True or first(state, "failure_of_failure") is not True:
        result["view"] = "WAIT"
        result["reasons"] = ["a failed-failure perspective requires both the initial failure and its failure"]
        return result
    if not explicitly_confirmed(first(state, "failed_failure_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["failure-of-failure direction is not explicitly confirmed"]
        return result
    return with_direction(result, state, signal, "the first breakout failure itself failed and the recorded direction is confirmed")
