"""Nison three-line-break trend and turnaround perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_three_line_break"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_three_line_direction",
    "nison_three_line_consecutive",
    "nison_three_line_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    consecutive = number(first(state, "nison_three_line_consecutive"))
    if consecutive is None or consecutive < 3:
        result["view"] = "WAIT"
        result["reasons"] = ["alternating lines are not the source three-line-break trend condition"]
        return result
    if not volman_truth(first(state, "nison_three_line_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["three-line-break direction has not closed with confirmation"]
        return result
    direction = normalized_status(first(state, "nison_three_line_direction"))
    if direction == "up":
        return with_direction(result, state, "BUY", "three consecutive white-line trend is confirmed")
    if direction == "down":
        return with_direction(result, state, "SELL", "three consecutive black-line trend is confirmed")
    result["view"] = "WAIT"
    result["reasons"] = ["three-line-break direction is unresolved"]
    return result
