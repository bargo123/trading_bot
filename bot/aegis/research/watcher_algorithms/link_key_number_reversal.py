"""Marcel Link's psychological key-number reversal checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_key_number_reversal"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_approach_direction",
    "link_key_number_distance_ticks",
    "link_key_number_rejection",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    distance = number(first(state, "link_key_number_distance_ticks"))
    approach = normalized_status(first(state, "link_approach_direction"))
    if distance is None or not 0 <= distance <= 10 or first(state, "link_key_number_rejection") is not True:
        result["reasons"] = ["price is not rejected within ten ticks of the key number"]
        return result
    signal = "BUY" if approach == "down" else "SELL" if approach == "up" else None
    if signal is None:
        result["reasons"] = ["the key-number approach direction is not observed"]
        return result
    return with_direction(result, state, signal, "psychological key number rejected the approach")
