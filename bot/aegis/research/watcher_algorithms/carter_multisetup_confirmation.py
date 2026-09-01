"""Carter's pivot-plus-Scalper-Alert combination as a research perspective."""
from __future__ import annotations

from ._common import absent, base, direction, first, normalized_status, values, with_direction

ALGORITHM_ID = "carter_multisetup_confirmation"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_multisetup_pivot_view",
    "carter_multisetup_scalper_view",
    "carter_multisetup_data_provenance",
)


def _observed(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in provenance for token in ("observed", "measured", "historical", "live"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _observed(first(state, "carter_multisetup_data_provenance")):
        missing.append("carter_multisetup_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pivot = direction(first(state, "carter_multisetup_pivot_view"))
    scalper = direction(first(state, "carter_multisetup_scalper_view"))
    result["directional_claim"] = True
    if pivot is None or scalper is None:
        result["carter_multisetup_action"] = "INVALID_SETUP_VIEW"
        result["reasons"] = ["both the pivot and Scalper Alert views must have an unambiguous observed direction"]
        return result

    result["carter_multisetup_views"] = {"pivot": pivot, "scalper_alert": scalper}
    if pivot != scalper:
        result["carter_multisetup_action"] = "CONFLICT_WAIT"
        result["carter_multisetup_agreement_count"] = 0
        result["reasons"] = ["the named pivot and Scalper Alert setups do not agree"]
        return result

    result["carter_multisetup_action"] = "COMBINED_CONFIRMATION"
    result["carter_multisetup_agreement_count"] = 2
    return with_direction(result, state, pivot, "the named pivot and Scalper Alert setups agree")
