"""Schwager's stronger reversal-day definition from Getting Started in Technical Analysis."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "schwager_restrictive_reversal_day"
SOURCES = ("Getting Started in Technical Analysis",)
KEYS = (
    "schwager_reversal_day_trend",
    "schwager_reversal_day_extreme",
    "schwager_reversal_day_close_relation",
    "schwager_reversal_day_confirmation",
    "schwager_reversal_day_data_provenance",
)


def _truth(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance(value):
    label = normalized_status(value)
    return bool(label) and "observed" in label and any(token in label for token in ("bar", "price", "quote")) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance(first(state, "schwager_reversal_day_data_provenance")):
        missing.append("schwager_reversal_day_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "schwager_reversal_day_trend"))
    extreme = normalized_status(first(state, "schwager_reversal_day_extreme"))
    relation = normalized_status(first(state, "schwager_reversal_day_close_relation"))
    expected = (
        ("new high", "below prior low", "SELL") if trend == "up"
        else ("new low", "above prior high", "BUY") if trend == "down"
        else None
    )
    if expected is None or (extreme, relation) != expected[:2]:
        result["schwager_reversal_day_assessment"] = "RESTRICTIVE_DEFINITION_NOT_MET"
        result["reasons"] = ["the stronger reversal-day rule requires a new extreme and a close beyond the prior day's opposing extreme"]
        return result
    if not _truth(first(state, "schwager_reversal_day_confirmation")):
        result["schwager_reversal_day_assessment"] = "CONFIRMATION_UNRESOLVED"
        result["reasons"] = ["the restrictive reversal day is not explicitly confirmed"]
        return result
    result["schwager_reversal_day_assessment"] = "RESTRICTIVE_REVERSAL_DAY"
    result["warnings"] = ["the source reports frequent premature reversal-day signals; this is a research warning, not proof of a major top or bottom"]
    return with_direction(result, state, expected[2], "the reversal day closes beyond the prior day's low/high rather than merely beyond its close")
