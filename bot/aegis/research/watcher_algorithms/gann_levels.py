"""Gann level/angle perspective when level annotations are supplied."""
from __future__ import annotations

from ._common import base, direction, strings, values, with_direction

ALGORITHM_ID = "gann_levels"
SOURCES = (
    "Technical Analysis of the Financial Markets — John J. Murphy",
    "Mastering the Trade — John F. Carter",
)
KEYS = ("gann_state", "gann_direction", "gann_confirmation", "gann_level", "gann_angle", "gann_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("gann_level_annotation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, *KEYS)
    if any(token in text for token in ("invalid", "failed", "unconfirmed", "rejected")):
        result["view"] = "WAIT"
        result["reasons"] = ["Gann level or angle has failed or lacks confirmation"]
        return result
    if not any(token in text for token in ("confirmed", "hold", "break", "reclaim")):
        result["view"] = "WAIT"
        result["reasons"] = ["Gann annotation is present without a confirmed interaction"]
        return result
    signal = direction(text)
    if signal:
        return with_direction(result, state, signal, "confirmed Gann level interaction has a direction")
    result["view"] = "WAIT"
    result["reasons"] = ["Gann level interaction has no unambiguous direction"]
    return result
