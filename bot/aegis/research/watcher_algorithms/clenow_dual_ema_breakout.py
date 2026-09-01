"""Clenow's dual-EMA trend filter applied to a confirmed breakout."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "clenow_dual_ema_breakout"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_timeframe",
    "clenow_fast_ema",
    "clenow_slow_ema",
    "clenow_trend_filter",
    "clenow_breakout_direction",
    "clenow_breakout_confirmation",
    "clenow_atr",
    "clenow_risk_factor",
    "clenow_data_provenance",
)


def _missing(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "clenow_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("clenow_data_provenance")
    return list(dict.fromkeys(missing))


def evaluate(state):
    missing = _missing(state)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "clenow_timeframe")) != "daily":
        result["view"] = "WAIT"
        result["reasons"] = ["the source core model is defined on daily bars"]
        return result
    fast = number(first(state, "clenow_fast_ema"))
    slow = number(first(state, "clenow_slow_ema"))
    atr = number(first(state, "clenow_atr"))
    risk_factor = number(first(state, "clenow_risk_factor"))
    if fast is None or slow is None or atr is None or atr <= 0 or risk_factor is None or risk_factor <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["EMA, ATR, and volatility-adjusted risk inputs are not valid"]
        return result
    trend = normalized_status(first(state, "clenow_trend_filter"))
    ema_trend = "up" if fast > slow else "down" if fast < slow else "range"
    if trend != ema_trend or trend == "range":
        result["view"] = "WAIT"
        result["reasons"] = ["dual-EMA trend filter is not directional"]
        return result
    if not volman_truth(first(state, "clenow_breakout_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["breakout has not been confirmed"]
        return result
    breakout = normalized_status(first(state, "clenow_breakout_direction"))
    if trend == "up" and breakout == "up":
        return with_direction(result, state, "BUY", "confirmed breakout agrees with the dual-EMA trend filter")
    if trend == "down" and breakout == "down":
        return with_direction(result, state, "SELL", "confirmed breakout agrees with the dual-EMA trend filter")
    result["view"] = "WAIT"
    result["reasons"] = ["breakout direction conflicts with the dual-EMA trend filter"]
    return result
