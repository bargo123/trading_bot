"""Structural support/resistance and role-reversal algorithm."""
from __future__ import annotations

from ._common import absent, base, strings, values, with_direction

ALGORITHM_ID = "support_resistance"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
)
KEYS = (
    "support", "resistance", "support_level", "resistance_level", "level_role",
    "level_state", "distance_to_support", "distance_to_resistance", "rejection",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("support_resistance_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("support_hold", "support reclaimed", "resistance turned support", "bullish rejection")):
        return with_direction(result, state, "BUY", "support or role-reversal evidence favors an upside test")
    if any(token in text for token in ("resistance_hold", "resistance rejected", "support turned resistance", "bearish rejection")):
        return with_direction(result, state, "SELL", "resistance or role-reversal evidence favors a downside test")
    result["view"] = "WAIT"
    result["reasons"] = ["levels are recorded without a confirmed hold, rejection, or role reversal"]
    return result
