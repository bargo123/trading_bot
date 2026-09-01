"""The Alexander price-return filter described in Chan's book."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "chan_alexander_filter"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_alexander_reference_price",
    "chan_alexander_current_price",
    "chan_alexander_subsequent_peak",
    "chan_alexander_threshold",
    "chan_alexander_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "chan_alexander_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("chan_alexander_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    reference = number(first(state, "chan_alexander_reference_price"))
    current = number(first(state, "chan_alexander_current_price"))
    peak = number(first(state, "chan_alexander_subsequent_peak"))
    threshold = number(first(state, "chan_alexander_threshold"))
    if any(value is None for value in (reference, current, peak, threshold)) or min(reference, current, peak) <= 0 or threshold <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["reference, current, peak, and threshold must be valid positive observations"]
        return result
    buy_signal = current >= reference * (1.0 + threshold)
    sell_signal = current <= peak * (1.0 - threshold)
    if buy_signal == sell_signal:
        result["view"] = "WAIT"
        result["reasons"] = ["Alexander filter has no unambiguous one-sided threshold break"]
        return result
    signal = "BUY" if buy_signal else "SELL"
    return with_direction(result, state, signal, "price-return threshold filter gives an unambiguous direction")
