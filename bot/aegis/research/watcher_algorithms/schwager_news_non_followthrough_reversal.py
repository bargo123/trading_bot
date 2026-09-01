"""Schwager's reversal warning when important news fails to attract follow-through."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, with_direction


ALGORITHM_ID = "schwager_news_non_followthrough_reversal"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_news_direction",
    "schwager_news_importance",
    "schwager_news_followthrough",
    "schwager_news_data_provenance",
)


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upside", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downside", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def _false_observed(value):
    return value is False or normalized_status(value) in {
        "false", "no", "failed", "not followed", "no follow through", "without follow through",
    }


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "schwager_news_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("schwager_news_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    news_direction = _direction(first(state, "schwager_news_direction"))
    importance = normalized_status(first(state, "schwager_news_importance"))
    if news_direction is None or importance not in {"significant", "important", "major"}:
        result["schwager_news_assessment"] = "NEWS_INPUT_INVALID"
        result["view"] = "WAIT"
        result["reasons"] = ["a significant observed news direction is required"]
        return result
    if not _false_observed(first(state, "schwager_news_followthrough")):
        result["schwager_news_assessment"] = "FOLLOWTHROUGH_PRESENT_OR_UNRESOLVED"
        result["view"] = "WAIT"
        result["reasons"] = ["the reversal observation requires significant news to fail to attract follow-through"]
        return result

    signal = "SELL" if news_direction == "BUY" else "BUY"
    result["schwager_news_assessment"] = (
        "BULLISH_NEWS_FAILURE_REVERSAL" if news_direction == "BUY" else "BEARISH_NEWS_FAILURE_REVERSAL"
    )
    result["warnings"] = ["non-follow-through is a reversal hypothesis and requires cost-aware outcome testing"]
    return with_direction(result, state, signal, "significant news failed to produce the expected directional follow-through")
