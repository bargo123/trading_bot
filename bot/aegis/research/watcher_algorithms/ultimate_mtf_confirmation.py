"""The Ultimate Forex Trading System's higher-timeframe confirmation study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "ultimate_mtf_confirmation"
SOURCES = ("Mostafa Afshari — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_mtf_entry_direction",
    "ultimate_mtf_higher_direction",
    "ultimate_mtf_higher_timeframe",
    "ultimate_mtf_agreement_confirmed",
    "ultimate_data_provenance",
)


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


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
    entry = _direction(first(state, "ultimate_mtf_entry_direction"))
    higher = _direction(first(state, "ultimate_mtf_higher_direction"))
    timeframe = normalized_status(first(state, "ultimate_mtf_higher_timeframe"))
    if entry is None or higher is None or not timeframe:
        result["ultimate_mtf_assessment"] = "DIRECTION_OR_TIMEFRAME_INVALID"
        result["reasons"] = ["entry and higher-timeframe directions must be explicit"]
        return result
    if entry != higher or not _truthy(first(state, "ultimate_mtf_agreement_confirmed")):
        result["ultimate_mtf_assessment"] = "TIMEFRAME_DISAGREEMENT"
        result["reasons"] = ["the source uses the longer chart to confirm or veto the entry direction"]
        return result
    result["ultimate_mtf_assessment"] = "CONFIRMED_AGREEMENT"
    result["ultimate_mtf_higher_timeframe"] = timeframe
    return with_direction(result, state, entry, "the entry direction agrees with the observed higher-timeframe context")
