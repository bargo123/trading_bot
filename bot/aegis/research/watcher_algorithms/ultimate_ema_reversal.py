"""The Ultimate Forex Trading System's EMA(9)/EMA(15) reversal study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_ema_reversal"
SOURCES = ("Mostafa Afshari — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_ema_fast_period",
    "ultimate_ema_slow_period",
    "ultimate_ema_cross_direction",
    "ultimate_ema_cross_confirmed",
    "ultimate_data_provenance",
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
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    fast = number(first(state, "ultimate_ema_fast_period"))
    slow = number(first(state, "ultimate_ema_slow_period"))
    if fast != 9 or slow != 15:
        result["ultimate_ema_assessment"] = "EMA_PERIODS_INVALID"
        result["reasons"] = ["the source reversal proxy requires EMA(9) crossing EMA(15)"]
        return result
    if not _truthy(first(state, "ultimate_ema_cross_confirmed")):
        result["ultimate_ema_assessment"] = "CROSS_NOT_CONFIRMED"
        result["reasons"] = ["the EMA cross must be observed and confirmed at the decision time"]
        return result
    signal = _direction(first(state, "ultimate_ema_cross_direction"))
    if signal is None:
        result["ultimate_ema_assessment"] = "CROSS_DIRECTION_INVALID"
        result["reasons"] = ["the observed EMA cross direction is not explicit"]
        return result
    result["ultimate_ema_assessment"] = "CONFIRMED_CROSS"
    result["ultimate_ema_periods"] = (int(fast), int(slow))
    return with_direction(result, state, signal, "the confirmed EMA(9)/EMA(15) cross supplies the source's reversal warning")
