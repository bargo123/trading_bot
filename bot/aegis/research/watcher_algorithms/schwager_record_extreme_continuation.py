"""Schwager's held-record-high/low continuation observation."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction


ALGORITHM_ID = "schwager_record_extreme_continuation"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_record_extreme",
    "schwager_record_extreme_held",
    "schwager_record_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "schwager_record_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("schwager_record_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    extreme = normalized_status(first(state, "schwager_record_extreme"))
    signal = (
        "BUY" if extreme in {"new high", "record high", "new historical high", "all time high"}
        else "SELL" if extreme in {"new low", "record low", "new historical low", "all time low"}
        else None
    )
    if signal is None:
        result["schwager_record_assessment"] = "EXTREME_UNRECOGNIZED"
        result["view"] = "WAIT"
        result["reasons"] = ["the copied chart must identify a new or record high/low"]
        return result
    if not volman_truth(first(state, "schwager_record_extreme_held")):
        result["schwager_record_assessment"] = "RECORD_NOT_HELD"
        result["view"] = "WAIT"
        result["reasons"] = ["the source continuation observation requires the new record to hold"]
        return result

    result["schwager_record_assessment"] = (
        "HELD_RECORD_HIGH_CONTINUATION" if signal == "BUY" else "HELD_RECORD_LOW_CONTINUATION"
    )
    result["warnings"] = ["this is a continuation hypothesis, not proof that a record cannot reverse"]
    return with_direction(result, state, signal, "the observed record extreme held, supporting continuation in its direction")
