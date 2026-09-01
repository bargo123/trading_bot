"""Schwager's delayed, unfilled-island reversal validation perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_island_reversal_validation"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_island_type",
    "schwager_island_first_gap_direction",
    "schwager_island_second_gap_direction",
    "schwager_island_days_since_completion",
    "schwager_island_gap_filled",
    "schwager_island_confirmation",
    "schwager_island_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _false_observed(value) -> bool:
    return value is False or normalized_status(value) in {"false", "no", "not filled", "unfilled", "open"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and any(token in label for token in ("bar", "price", "quote")) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_island_data_provenance")):
        missing.append("schwager_island_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    kind = normalized_status(first(state, "schwager_island_type"))
    first_gap = normalized_status(first(state, "schwager_island_first_gap_direction"))
    second_gap = normalized_status(first(state, "schwager_island_second_gap_direction"))
    days = number(first(state, "schwager_island_days_since_completion"))
    if kind not in {"top", "bottom"} or first_gap not in {"up", "down"} or second_gap not in {"up", "down"} or days is None or days < 0:
        result["schwager_island_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["island type, opposing gap directions, and non-negative elapsed days must be observed"]
        return result
    if kind == "top" and (first_gap, second_gap) != ("up", "down"):
        result["schwager_island_assessment"] = "TOP_GAP_SEQUENCE_INVALID"
        result["reasons"] = ["an island top requires an upside first gap followed by a downside gap"]
        return result
    if kind == "bottom" and (first_gap, second_gap) != ("down", "up"):
        result["schwager_island_assessment"] = "BOTTOM_GAP_SEQUENCE_INVALID"
        result["reasons"] = ["an island bottom requires a downside first gap followed by an upside gap"]
        return result
    if days < 3:
        result["schwager_island_assessment"] = "CONFIRMATION_DELAY_INCOMPLETE"
        result["reasons"] = ["the source recommends waiting at least three days before treating the island as valid"]
        return result
    if not _false_observed(first(state, "schwager_island_gap_filled")):
        result["schwager_island_assessment"] = "RECENT_GAP_FILLED_OR_UNRESOLVED"
        result["reasons"] = ["the more recent gap must remain unfilled for the reversal signal to remain in force"]
        return result
    if not _truth(first(state, "schwager_island_confirmation")):
        result["schwager_island_assessment"] = "CONFIRMATION_UNRESOLVED"
        result["reasons"] = ["the island reversal has not been explicitly confirmed"]
        return result
    result["schwager_island_assessment"] = "VALID_TOP" if kind == "top" else "VALID_BOTTOM"
    return with_direction(result, state, "SELL" if kind == "top" else "BUY", "the opposing-gap island remained unfilled through the source's confirmation delay")
