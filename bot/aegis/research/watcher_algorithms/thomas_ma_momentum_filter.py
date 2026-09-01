"""The 10XROI system's separated 3/10-period moving-average filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "thomas_ma_momentum_filter"
SOURCES = ("LR Thomas — The 10XROI Trading System",)
KEYS = (
    "thomas_ma_fast_period",
    "thomas_ma_slow_period",
    "thomas_ma_direction",
    "thomas_ma_separation_observed",
    "thomas_candles_hug_fast_ma",
    "thomas_candles_touch_slow_ma",
    "thomas_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "thomas_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("thomas_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    fast = number(first(state, "thomas_ma_fast_period"))
    slow = number(first(state, "thomas_ma_slow_period"))
    direction = _direction(first(state, "thomas_ma_direction"))
    if fast != 3 or slow != 10 or direction is None:
        result["thomas_ma_assessment"] = "MA_INPUTS_INVALID"
        result["reasons"] = ["the source uses a directional 3-period fast average and 10-period slow average"]
        return result
    if not _truthy(first(state, "thomas_ma_separation_observed")) or not _truthy(first(state, "thomas_candles_hug_fast_ma")) or _truthy(first(state, "thomas_candles_touch_slow_ma")):
        result["thomas_ma_assessment"] = "WEAK_MOMENTUM"
        result["reasons"] = ["the source wants separated averages, candles hugging the fast average, and no repeated slow-average touches"]
        return result
    result["thomas_ma_assessment"] = "STRONG_MOMENTUM"
    return with_direction(result, state, direction, "the separated 3/10 averages and fast-average price behavior support momentum")
