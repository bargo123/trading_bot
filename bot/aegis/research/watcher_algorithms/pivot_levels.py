"""Prior-session pivot-level context and directional relation."""
from __future__ import annotations

from ._common import base, strings, values, with_direction

ALGORITHM_ID = "pivot_levels"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "John F. Carter — Mastering the Trade",
)
KEYS = (
    "previous_session_high", "previous_session_low", "previous_session_close", "pivot",
    "pivot_r1", "pivot_s1", "pivot_r2", "pivot_s2", "pivot_relation", "pivot_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("observed_prior_session_pivot",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    relation = strings(state, "pivot_relation")
    if relation == "above_pivot":
        return with_direction(result, state, "BUY", "price is above the observed prior-session pivot")
    if relation == "below_pivot":
        return with_direction(result, state, "SELL", "price is below the observed prior-session pivot")
    result["view"] = "WAIT"
    result["reasons"] = ["price is at the observed pivot and has not established directional separation"]
    return result
