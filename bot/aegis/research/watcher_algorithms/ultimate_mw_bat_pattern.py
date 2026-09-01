"""The Ultimate Forex Trading System's low-confidence M/W pattern context."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "ultimate_mw_bat_pattern"
SOURCES = ("Mostafa Afshari — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_mw_shape",
    "ultimate_mw_zone",
    "ultimate_mw_completed",
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
    shape = normalized_status(first(state, "ultimate_mw_shape"))
    zone = normalized_status(first(state, "ultimate_mw_zone"))
    signal = "SELL" if shape == "m" and zone == "resistance" else "BUY" if shape == "w" and zone == "support" else None
    if not _truthy(first(state, "ultimate_mw_completed")):
        result["ultimate_mw_assessment"] = "PATTERN_NOT_COMPLETED"
        result["reasons"] = ["the source treats an M/W shape as a rough estimate only after completion"]
        return result
    if signal is None:
        result["ultimate_mw_assessment"] = "ZONE_PATTERN_MISMATCH"
        result["reasons"] = ["the M pattern is source-aligned at resistance and the W pattern at support"]
        return result
    result["ultimate_mw_assessment"] = "LOW_CONFIDENCE_PATTERN"
    result["confidence_class"] = "LOW"
    result["reasons"] = ["the source explicitly describes M/W patterns as rough, less-accurate guidance"]
    return with_direction(result, state, signal, "the completed M/W shape is retained as low-confidence context")
