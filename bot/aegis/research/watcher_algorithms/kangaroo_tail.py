"""Elder kangaroo-tail rejection perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, number, strings, values, with_direction

ALGORITHM_ID = "kangaroo_tail"
SOURCES = ("Alexander Elder — The New Trading for a Living", "Al Brooks — Reading Price Charts Bar by Bar")
KEYS = ("tail_direction", "tail_context", "tail_confirmation", "tail_wick_ratio")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_long_wick_rejection",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction_text = strings(state, "tail_direction")
    context = strings(state, "tail_context")
    ratio = number(first(state, "tail_wick_ratio"))
    if ratio is None or ratio < 2 or not explicitly_confirmed(first(state, "tail_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["tail must be long enough and explicitly confirmed"]
        return result
    if "bull" in direction_text and "support" in context:
        return with_direction(result, state, "BUY", "confirmed bullish tail rejects support-side prices")
    if "bear" in direction_text and "resistance" in context:
        return with_direction(result, state, "SELL", "confirmed bearish tail rejects resistance-side prices")
    result["view"] = "WAIT"
    result["reasons"] = ["tail direction and structural level do not align"]
    return result
