"""Kathy Lien's post-release reactive-news checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "lien_reactive_news"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_news_phase",
    "lien_minutes_since_release",
    "lien_major_release",
    "lien_news_surprise_fraction",
    "lien_news_candle_reference_valid",
    "lien_surprise_direction",
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
    if normalized_status(first(state, "lien_news_phase")) != "post release":
        result["reasons"] = ["reactive entry must follow the major release"]
        return result
    minutes = number(first(state, "lien_minutes_since_release"))
    surprise = number(first(state, "lien_news_surprise_fraction"))
    if first(state, "lien_major_release") is not True or minutes is None or minutes < 5:
        result["reasons"] = ["the post-release observation is not at least five minutes after a major event"]
        return result
    if surprise is None or surprise <= 1.0 or first(state, "lien_news_candle_reference_valid") is not True:
        result["reasons"] = ["the release surprise is not greater than 100 percent with a valid news candle"]
        return result
    signal = normalized_status(first(state, "lien_surprise_direction")).upper()
    if signal not in {"BUY", "SELL"}:
        result["reasons"] = ["the surprise direction is not observed"]
        return result
    return with_direction(result, state, signal, "post-release follow-through confirms a greater-than-100-percent surprise")
