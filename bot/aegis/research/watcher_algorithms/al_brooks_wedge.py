"""Three-push wedge reversal perspective from Al Brooks."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, number, values, with_direction

ALGORITHM_ID = "al_brooks_wedge"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "wedge_reversal_direction",
    "wedge_pushes",
    "wedge_trendline_break",
    "wedge_overshoot",
    "wedge_confirmation",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_three_push_wedge",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pushes = number(first(state, "wedge_pushes"))
    signal = str(first(state, "wedge_reversal_direction") or "").strip().upper()
    if pushes is None or not pushes.is_integer() or pushes < 3 or signal not in {"BUY", "SELL"}:
        result["view"] = "WAIT"
        result["reasons"] = ["wedge reversal requires at least three pushes and an explicit direction"]
        return result
    if first(state, "wedge_trendline_break") is not True or not explicitly_confirmed(first(state, "wedge_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["three pushes alone are insufficient without a confirmed reversal context"]
        return result
    result["wedge_pushes"] = int(pushes)
    return with_direction(result, state, signal, "confirmed three-push wedge reversal is recorded")
