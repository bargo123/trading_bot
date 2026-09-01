"""Marcel Link's trade-the-market-not-the-news reaction fade checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "link_news_reaction_fade"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_expected_news_direction",
    "link_pre_news_direction",
    "link_news_result_in_line",
    "link_post_news_follow_through",
    "link_post_news_reversal_confirmed",
    "link_post_news_break_confirmed",
    "link_post_news_digest_minutes",
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
    expected = normalized_status(first(state, "link_expected_news_direction")).upper()
    pre_news = normalized_status(first(state, "link_pre_news_direction")).upper()
    minutes = number(first(state, "link_post_news_digest_minutes"))
    if expected not in {"BUY", "SELL"} or pre_news != expected:
        result["reasons"] = ["the pre-news market direction does not match the expected reaction"]
        return result
    if first(state, "link_news_result_in_line") is not True or first(state, "link_post_news_follow_through") is not False:
        result["reasons"] = ["the release did not confirm an expected move that then failed"]
        return result
    if first(state, "link_post_news_reversal_confirmed") is not True or first(state, "link_post_news_break_confirmed") is not True or minutes is None or minutes < 30:
        result["reasons"] = ["the market has not digested the release and confirmed the reversal break"]
        return result
    return with_direction(result, state, "SELL" if expected == "BUY" else "BUY", "expected news failed to produce follow-through after digestion")
