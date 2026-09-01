"""Nison spring/upthrust failed-break and reclaim perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_spring_upthrust"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_western_event",
    "nison_event_level_type",
    "nison_event_breach_confirmed",
    "nison_event_failed_hold",
    "nison_event_reclaim_direction",
    "nison_event_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not all(
        volman_truth(first(state, key))
        for key in ("nison_event_breach_confirmed", "nison_event_failed_hold", "nison_event_confirmation")
    ):
        result["view"] = "WAIT"
        result["reasons"] = ["spring/upthrust requires a confirmed breach, failed hold, and reclaim"]
        return result
    event = normalized_status(first(state, "nison_western_event"))
    level = normalized_status(first(state, "nison_event_level_type"))
    reclaim = normalized_status(first(state, "nison_event_reclaim_direction"))
    if event == "spring" and level == "support" and reclaim == "up":
        result["nison_event_assessment"] = "SPRING_RECLAIM"
        return with_direction(result, state, "BUY", "price failed below support and reclaimed it")
    if event == "upthrust" and level == "resistance" and reclaim == "down":
        result["nison_event_assessment"] = "UPTHRUST_RECLAIM"
        return with_direction(result, state, "SELL", "price failed above resistance and fell back below it")
    result["view"] = "WAIT"
    result["reasons"] = ["spring/upthrust event, level, and reclaim direction do not agree"]
    return result
