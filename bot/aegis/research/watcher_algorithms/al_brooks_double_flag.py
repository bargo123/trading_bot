"""Double-bottom bull-flag and double-top bear-flag perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, normalized_status, values, with_direction

ALGORITHM_ID = "al_brooks_double_flag"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "double_flag_type",
    "double_flag_second_test",
    "double_flag_confirmation",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_double_top_bottom_flag",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    flag = normalized_status(first(state, "double_flag_type"))
    test = normalized_status(first(state, "double_flag_second_test"))
    signal = "BUY" if "double bottom bull flag" in flag else "SELL" if "double top bear flag" in flag else None
    if signal is None or not any(token in test for token in ("held", "reclaimed", "confirmed")) or "failed" in test:
        result["view"] = "WAIT"
        result["reasons"] = ["double flag requires a held second test in the explicitly named continuation pattern"]
        return result
    if not explicitly_confirmed(first(state, "double_flag_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["double flag second test is not explicitly confirmed"]
        return result
    return with_direction(result, state, signal, "confirmed double-bottom/top continuation flag is recorded")
