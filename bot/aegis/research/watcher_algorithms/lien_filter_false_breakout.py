"""Kathy Lien's 20-day extreme / two-day reversal false-breakout filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_filter_false_breakout"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_original_extreme",
    "lien_reversal_extreme",
    "lien_reversal_days",
    "lien_rebreak_days",
    "lien_original_extreme_rebroken",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "lien_data_provenance")):
        missing.append("lien_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    original = normalized_status(first(state, "lien_original_extreme"))
    reversal = normalized_status(first(state, "lien_reversal_extreme"))
    reversal_days = number(first(state, "lien_reversal_days"))
    rebreak_days = number(first(state, "lien_rebreak_days"))
    if reversal_days is None or not 0 < reversal_days <= 3 or rebreak_days is None or not 0 < rebreak_days <= 3:
        result["reasons"] = ["the reversal and rebreak must each occur within the source three-day windows"]
        return result
    if first(state, "lien_original_extreme_rebroken") is not True:
        result["reasons"] = ["the original 20-day extreme has not been rebroken"]
        return result
    candidate_side = side(state)
    signal = None
    if original == "20 day high" and reversal == "2 day low":
        signal = "BUY"
    elif original == "20 day low" and reversal == "2 day high":
        signal = "SELL"
    if signal is None:
        result["reasons"] = ["the 20-day extreme and two-day reversal are not a valid directional pair"]
        return result
    return with_direction(result, state, signal, "20-day extreme, two-day flush, and timely rebreak form the filtered breakout")
