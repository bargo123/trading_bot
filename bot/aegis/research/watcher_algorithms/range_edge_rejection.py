"""Range-edge rejection and balanced-auction algorithm."""
from __future__ import annotations

from ._common import absent, base, strings, values, with_direction

ALGORITHM_ID = "range_edge_rejection"
SOURCES = (
    "Al Brooks — Trading Price Action Trading Ranges",
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Adam Grimes — The Art and Science of Technical Analysis",
)
KEYS = ("range_state", "range_position", "range_edge_rejection", "range_high", "range_low", "range_width", "rejection", "balance_state")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("range_and_edge_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("bullish rejection", "lower_edge_reclaimed", "low_reclaimed", "support_rejection")):
        return with_direction(result, state, "BUY", "lower range edge rejection or reclaim is recorded")
    if any(token in text for token in ("bearish rejection", "upper_edge_rejected", "high_rejected", "resistance_rejection")):
        return with_direction(result, state, "SELL", "upper range edge rejection or failure is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["range is present without a confirmed edge rejection or reclaim"]
    return result
