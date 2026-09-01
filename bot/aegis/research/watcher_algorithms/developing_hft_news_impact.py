"""Verified event-impact perspective described in the HFT source."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "developing_hft_news_impact"
SOURCES = ("Developing High-Frequency Trading Systems",)
KEYS = (
    "developing_hft_news_direction",
    "developing_hft_news_release_age_s",
    "developing_hft_news_relevance",
    "developing_hft_news_window_open",
    "developing_hft_news_expected_net_edge",
    "developing_hft_news_observation_n",
    "developing_hft_news_provenance",
    "developing_hft_news_confirmation",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "rumor", "unverified")):
        return False
    return "timestamped" in label and ("public" in label or "verified" in label or "news feed" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "developing_hft_news_provenance")):
        missing.append("developing_hft_news_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    age = number(first(state, "developing_hft_news_release_age_s"))
    relevance = number(first(state, "developing_hft_news_relevance"))
    edge = number(first(state, "developing_hft_news_expected_net_edge"))
    observations = number(first(state, "developing_hft_news_observation_n"))
    direction = normalized_status(first(state, "developing_hft_news_direction")).upper()
    if None in {age, relevance, edge, observations} or age < 0 or not 0 <= relevance <= 1 or observations <= 0:
        result["developing_hft_news_assessment"] = "UNKNOWN"
        result["reasons"] = ["event impact requires finite age, relevance, edge, and observation count"]
        return result
    if first(state, "developing_hft_news_window_open") is not True:
        result["developing_hft_news_assessment"] = "WINDOW_CLOSED"
        result["reasons"] = ["the observed news event is outside its explicitly supplied decision window"]
        return result
    if not explicitly_confirmed(first(state, "developing_hft_news_confirmation")) or relevance <= 0 or edge <= 0:
        result["developing_hft_news_assessment"] = "INSUFFICIENT_EDGE_OR_CONFIRMATION"
        result["reasons"] = ["event direction is not confirmed with positive after-cost economics"]
        return result
    if direction not in {"BUY", "SELL"}:
        result["developing_hft_news_assessment"] = "UNKNOWN_DIRECTION"
        result["reasons"] = ["verified event has no unambiguous directional classification"]
        return result
    result["developing_hft_news_assessment"] = "ACTIONABLE_EVENT"
    return with_direction(result, state, direction, "verified timestamped event has confirmed direction and positive net edge")
