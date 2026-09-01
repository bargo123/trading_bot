"""Laurentiu Damir's trend, Fibonacci, and completed-pattern confluence study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "damir_fib_confluence_reversal"
SOURCES = ("Laurentiu Damir — Trade the Price Action",)
KEYS = (
    "damir_trend",
    "damir_chart_timeframe",
    "damir_daily_ema200_aligned",
    "damir_correction_observed",
    "damir_fibonacci_retracement",
    "damir_reversal_pattern",
    "damir_pattern_completed",
    "damir_entry_after_pattern_close",
    "damir_stop_pips",
    "damir_target_pips",
    "damir_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "damir_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("damir_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "damir_trend"))
    timeframe = normalized_status(first(state, "damir_chart_timeframe"))
    pattern = normalized_status(first(state, "damir_reversal_pattern"))
    fib = number(first(state, "damir_fibonacci_retracement"))
    stop = number(first(state, "damir_stop_pips"))
    target = number(first(state, "damir_target_pips"))
    if trend not in {"up", "uptrend", "bull", "bullish", "down", "downtrend", "bear", "bearish"} or timeframe != "4h":
        result["view"] = "WAIT"
        result["reasons"] = ["the source setup requires an observed 4H trend"]
        return result
    if not _truthy(first(state, "damir_daily_ema200_aligned")) or not _truthy(first(state, "damir_correction_observed")):
        result["view"] = "WAIT"
        result["reasons"] = ["daily EMA(200) alignment and an opposing correction are required"]
        return result
    if fib is None or min(abs(fib - level) for level in (50.0, 61.8, 78.2)) > 0.15:
        result["view"] = "WAIT"
        result["reasons"] = ["price is not at one of the source's 50%, 61.8%, or 78.2% retracement levels"]
        return result
    named_patterns = (
        "hammer",
        "engulfing",
        "morning star",
        "evening star",
        "dark cloud",
        "piercing",
        "two candle",
        "three candle",
    )
    if not any(token in pattern for token in named_patterns):
        result["view"] = "WAIT"
        result["reasons"] = ["a named source reversal candlestick pattern is required"]
        return result
    if not _truthy(first(state, "damir_pattern_completed")) or not _truthy(first(state, "damir_entry_after_pattern_close")):
        result["view"] = "WAIT"
        result["reasons"] = ["a completed reversal candle/pattern is required before entry"]
        return result
    if any(value is None for value in (stop, target)) or stop <= 0 or target <= stop:
        result["view"] = "WAIT"
        result["reasons"] = ["source geometry requires positive reward greater than risk"]
        return result
    signal = "BUY" if trend in {"up", "uptrend", "bull", "bullish"} else "SELL"
    result["damir_geometry"] = {"stop_pips": stop, "target_pips": target, "reward_risk": target / stop}
    result["damir_confluence"] = {"fibonacci": fib, "pattern": pattern, "daily_ema200_aligned": True}
    return with_direction(result, state, signal, "trend, daily EMA, Fibonacci retracement, and closed reversal pattern align")
