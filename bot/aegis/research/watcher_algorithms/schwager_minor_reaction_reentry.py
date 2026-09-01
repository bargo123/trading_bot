"""Schwager's minor-reaction trend-resumption entry perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_minor_reaction_reentry"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_reaction_trend",
    "schwager_reaction_pattern",
    "schwager_reaction_lookback_n",
    "schwager_reaction_resumption_trigger",
    "schwager_reaction_lookback_x",
    "schwager_reaction_resumption_confirmed",
    "schwager_reaction_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _direction(value) -> str | None:
    label = normalized_status(value)
    if label in {"up", "uptrend", "bull", "bullish"}:
        return "UP"
    if label in {"down", "downtrend", "bear", "bearish"}:
        return "DOWN"
    return None


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and any(token in label for token in ("bar", "price", "quote")) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def _positive_integer(value) -> bool:
    parsed = number(value)
    return parsed is not None and parsed > 0 and parsed.is_integer()


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_reaction_data_provenance")):
        missing.append("schwager_reaction_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = _direction(first(state, "schwager_reaction_trend"))
    pattern = normalized_status(first(state, "schwager_reaction_pattern"))
    trigger = normalized_status(first(state, "schwager_reaction_resumption_trigger"))
    n = number(first(state, "schwager_reaction_lookback_n"))
    x = number(first(state, "schwager_reaction_lookback_x"))
    if trend is None or not _positive_integer(n) or not _positive_integer(x):
        result["schwager_reaction_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["trend and positive integer N/X lookbacks must be observed"]
        return result
    if not _truth(first(state, "schwager_reaction_resumption_confirmed")):
        result["schwager_reaction_assessment"] = "RESUMPTION_UNCONFIRMED"
        result["reasons"] = ["the minor reaction is present without a confirmed close resuming the major trend"]
        return result
    if trend == "UP" and pattern == "n day low" and trigger == "close above x day high":
        result["schwager_reaction_assessment"] = "UPTREND_RESUMPTION"
        result["schwager_reaction_n"] = int(n)
        result["schwager_reaction_x"] = int(x)
        return with_direction(result, state, "BUY", "an observed N-day low was followed by a close above the recent X-day high")
    if trend == "DOWN" and pattern == "n day high" and trigger == "close below x day low":
        result["schwager_reaction_assessment"] = "DOWNTREND_RESUMPTION"
        result["schwager_reaction_n"] = int(n)
        result["schwager_reaction_x"] = int(x)
        return with_direction(result, state, "SELL", "an observed N-day high was followed by a close below the recent X-day low")
    result["schwager_reaction_assessment"] = "REACTION_TRIGGER_MISMATCH"
    result["reasons"] = ["the reaction extreme and resumption close do not match the prevailing trend"]
    return result
