"""Kathy Lien's pre-release proactive-news checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_proactive_news"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_news_phase",
    "lien_minutes_to_release",
    "lien_major_release",
    "lien_range_lookback_hours",
    "lien_stop_reference_valid",
    "lien_surprise_bias",
    "lien_event_provenance",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    for key in ("lien_data_provenance", "lien_event_provenance"):
        if not _provenance_ok(first(state, key)):
            missing.append(key)
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "lien_news_phase")) != "pre release":
        result["reasons"] = ["proactive entry must occur before the major release"]
        return result
    minutes = number(first(state, "lien_minutes_to_release"))
    lookback = number(first(state, "lien_range_lookback_hours"))
    if first(state, "lien_major_release") is not True or minutes is None or not 0 < minutes <= 20:
        result["reasons"] = ["the event is not a verified major release within the 20-minute entry window"]
        return result
    if lookback != 2 or first(state, "lien_stop_reference_valid") is not True:
        result["reasons"] = ["the two-hour range and structural stop reference are not verified"]
        return result
    signal = normalized_status(first(state, "lien_surprise_bias")).upper()
    if signal not in {"BUY", "SELL"}:
        result["reasons"] = ["the pre-release directional bias is not observed"]
        return result
    return with_direction(result, state, signal, "verified major event, two-hour range, and directional pre-release bias")
