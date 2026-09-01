"""Kathy Lien's split pre-release/post-release news trade checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_combined_news"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_news_phase",
    "lien_minutes_to_release",
    "lien_minutes_since_release",
    "lien_major_release",
    "lien_initial_half_bias",
    "lien_post_release_surprise_agrees",
    "lien_second_entry_allowed",
    "lien_second_entry_timing_valid",
    "lien_stop_pips",
    "lien_first_target_pips",
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
    if normalized_status(first(state, "lien_news_phase")) != "pre and post":
        result["reasons"] = ["the combined plan requires both pre- and post-release phases"]
        return result
    before = number(first(state, "lien_minutes_to_release"))
    after = number(first(state, "lien_minutes_since_release"))
    stop = number(first(state, "lien_stop_pips"))
    target = number(first(state, "lien_first_target_pips"))
    if first(state, "lien_major_release") is not True or before is None or not 0 < before <= 20 or after is None or after < 5:
        result["reasons"] = ["the split entries are outside the 20-minute pre-release and five-minute post-release windows"]
        return result
    if first(state, "lien_post_release_surprise_agrees") is not True or first(state, "lien_second_entry_allowed") is not True:
        result["reasons"] = ["the post-release evidence does not confirm the initial directional thesis"]
        return result
    if first(state, "lien_second_entry_timing_valid") is not True or stop is None or stop != 45 or target is None or target != 45:
        result["reasons"] = ["the second entry timing or 45-pip risk/first-target plan is not verified"]
        return result
    signal = normalized_status(first(state, "lien_initial_half_bias")).upper()
    if signal not in {"BUY", "SELL"}:
        result["reasons"] = ["the initial half-position bias is not observed"]
        return result
    return with_direction(result, state, signal, "the initial half is confirmed by aligned post-release evidence")
