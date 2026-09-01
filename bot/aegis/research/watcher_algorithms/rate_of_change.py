"""Rate-of-change momentum perspective using point-in-time returns."""
from __future__ import annotations

from ._common import base, first, number, text, values, with_direction

ALGORITHM_ID = "rate_of_change"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Robert Carver — Systematic Trading",
    "Wesley R. Gray — Quantitative Momentum",
)
KEYS = (
    "roc", "roc_1", "roc_3", "roc_5", "roc_10", "roc_20",
    "roc_1s", "roc_3s", "roc_5s", "roc_10s", "roc_20s",
    "roc_state", "roc_direction",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("rate_of_change",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    state_text = text(first(state, "roc_state", "roc_direction")).lower()
    if any(token in state_text for token in ("negative", "down", "bear", "falling")):
        return with_direction(result, state, "SELL", "rate of change is negative")
    if any(token in state_text for token in ("positive", "up", "bull", "rising")):
        return with_direction(result, state, "BUY", "rate of change is positive")
    roc = number(first(state, "roc", "roc_1", "roc_3", "roc_5", "roc_10", "roc_20", "roc_1s", "roc_3s", "roc_5s", "roc_10s", "roc_20s"))
    if roc is None:
        result["view"] = "WAIT"
        result["reasons"] = ["rate-of-change fields are present but not numeric"]
    elif roc > 0:
        return with_direction(result, state, "BUY", "measured rate of change is positive")
    elif roc < 0:
        return with_direction(result, state, "SELL", "measured rate of change is negative")
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["rate of change is flat"]
    return result
