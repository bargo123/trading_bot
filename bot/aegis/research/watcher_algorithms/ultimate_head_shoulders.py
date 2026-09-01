"""The Ultimate Forex Trading System's right-shoulder pattern study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_head_shoulders"
SOURCES = ("Mostafa Afshari — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_hs_pattern",
    "ultimate_hs_left_head_complete",
    "ultimate_hs_right_shoulder_observed",
    "ultimate_hs_right_shoulder_overlap_pct",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = normalized_status(first(state, "ultimate_hs_pattern"))
    signal = {"head and shoulders": "SELL", "inverse head and shoulders": "BUY"}.get(pattern)
    if signal is None:
        result["ultimate_hs_assessment"] = "PATTERN_INVALID"
        result["reasons"] = ["the observed pattern must be head-and-shoulders or inverse head-and-shoulders"]
        return result
    overlap = number(first(state, "ultimate_hs_right_shoulder_overlap_pct"))
    if overlap is None or not 0 <= overlap <= 100:
        result["ultimate_hs_assessment"] = "OVERLAP_INVALID"
        result["reasons"] = ["right-shoulder overlap must be a finite percentage"]
        return result
    if overlap <= 80:
        result["ultimate_hs_assessment"] = "SHOULDER_OVERLAP_INSUFFICIENT"
        result["reasons"] = ["the source requires the right shoulder to overlap the left by more than 80 percent"]
        return result
    if not _truthy(first(state, "ultimate_hs_left_head_complete")) or not _truthy(first(state, "ultimate_hs_right_shoulder_observed")):
        result["ultimate_hs_assessment"] = "SHOULDER_SETUP_INCOMPLETE"
        result["reasons"] = ["the left shoulder/head context and an observed right shoulder are required"]
        return result
    result["ultimate_hs_assessment"] = "RIGHT_SHOULDER_SETUP"
    result["ultimate_hs_overlap_pct"] = overlap
    return with_direction(result, state, signal, "the overlapping right shoulder is the source's early pattern opportunity")
