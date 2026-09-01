"""Schwager's equity-curve deterioration warning perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "schwager_equity_deterioration_warning"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_equity_deterioration_observed",
    "schwager_equity_deterioration_kind",
    "schwager_equity_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "equity" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_equity_data_provenance")):
        missing.append("schwager_equity_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    kind = normalized_status(first(state, "schwager_equity_deterioration_kind"))
    recognized = {"abrupt decline", "precipitous decline", "sudden decline", "drawdown deterioration"}
    if kind not in recognized:
        result["schwager_equity_assessment"] = "EQUITY_STATE_UNCLASSIFIED"
        result["reasons"] = ["the copied equity curve does not identify a recognized deterioration state"]
        return result
    if _truth(first(state, "schwager_equity_deterioration_observed")):
        result["schwager_equity_assessment"] = "REDUCE_EXPOSURE_AND_REASSESS"
        result["warnings"] = ["an abrupt equity decline is a caution signal for reducing exposure and reassessing conditions"]
    else:
        result["schwager_equity_assessment"] = "Deterioration_NOT_OBSERVED"
        result["reasons"] = ["the deterioration label is present but not observed at the copied timestamp"]
    result["reasons"] = [*result.get("reasons", []), "this is a portfolio/research warning, not a directional trade instruction"]
    return result
