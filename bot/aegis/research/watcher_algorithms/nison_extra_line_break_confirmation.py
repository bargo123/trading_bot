"""Nison extra-line confirmation after a three-line-break turnaround."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_extra_line_break_confirmation"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_extra_confirmation_turnaround",
    "nison_extra_confirmation_line",
    "nison_extra_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_extra_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["extra confirmation requires a confirmed following same-color line"]
        return result
    turnaround = normalized_status(first(state, "nison_extra_confirmation_turnaround"))
    following = normalized_status(first(state, "nison_extra_confirmation_line"))
    if turnaround == "up" and following == "up":
        return with_direction(result, state, "BUY", "following white line supplies Nison's extra reversal confirmation")
    if turnaround == "down" and following == "down":
        return with_direction(result, state, "SELL", "following black line supplies Nison's extra reversal confirmation")
    result["view"] = "WAIT"
    result["reasons"] = ["extra confirmation line does not agree with the turnaround"]
    return result
