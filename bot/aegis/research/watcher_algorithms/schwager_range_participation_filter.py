"""Schwager's warning to minimize participation in hard-to-trade ranges."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "schwager_range_participation_filter"
SOURCES = ("Getting Started in Technical Analysis",)
KEYS = (
    "schwager_market_regime",
    "schwager_range_predictability",
    "schwager_range_strategy",
    "schwager_range_boundary_breach",
    "schwager_range_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and "range" in label


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_range_data_provenance")):
        missing.append("schwager_range_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    regime = normalized_status(first(state, "schwager_market_regime"))
    predictability = normalized_status(first(state, "schwager_range_predictability"))
    if regime not in {"range", "sideways"}:
        result["schwager_range_assessment"] = "NOT_A_RANGE"
        result["reasons"] = ["range participation guidance is not applicable outside an observed range"]
        return result
    if first(state, "schwager_range_boundary_breach") is True:
        result["schwager_range_assessment"] = "RANGE_INVALIDATED"
        result["reasons"] = ["the observed boundary breach invalidates the prior range context"]
        return result
    if predictability in {"low", "unpredictable", "unknown"}:
        result["schwager_range_assessment"] = "MINIMIZE_PARTICIPATION"
        result["warnings"] = ["the source describes ranges as difficult to predict and recommends minimizing participation"]
    else:
        result["schwager_range_assessment"] = "RANGE_CONTEXT"
    result["reasons"] = ["range context is a participation warning, not a directional signal"]
    return result
