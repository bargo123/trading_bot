"""Clenow's explicit 50/100 EMA-filtered 100-day breakout model."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "clenow_core_breakout"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_core_timeframe",
    "clenow_core_fast_ema",
    "clenow_core_slow_ema",
    "clenow_core_trend",
    "clenow_core_extreme_type",
    "clenow_core_breakout_confirmed",
    "clenow_core_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "clenow_core_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("clenow_core_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "clenow_core_timeframe")) != "daily":
        result["view"] = "WAIT"
        result["reasons"] = ["the source core breakout is defined on daily observations"]
        return result
    fast = number(first(state, "clenow_core_fast_ema"))
    slow = number(first(state, "clenow_core_slow_ema"))
    trend = normalized_status(first(state, "clenow_core_trend"))
    extreme = normalized_status(first(state, "clenow_core_extreme_type"))
    if fast is None or slow is None or fast <= 0 or slow <= 0 or trend not in {"up", "down"}:
        result["clenow_core_assessment"] = "INVALID_TREND_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["the 50/100 EMA ordering and declared trend must be positive and directional"]
        return result
    computed = "up" if fast > slow else "down" if fast < slow else "range"
    if computed != trend or extreme not in {"new 100 day high", "new 100 day low"}:
        result["clenow_core_assessment"] = "TREND_OR_EXTREME_MISMATCH"
        result["view"] = "WAIT"
        result["reasons"] = ["the source requires a 100-day extreme aligned with the 50/100 EMA trend"]
        return result
    if not volman_truth(first(state, "clenow_core_breakout_confirmed")):
        result["clenow_core_assessment"] = "BREAKOUT_UNCONFIRMED"
        result["view"] = "WAIT"
        result["reasons"] = ["the observed 100-day extreme is not confirmed"]
        return result
    if trend == "up" and extreme == "new 100 day high":
        result["clenow_core_assessment"] = "BUY_100_DAY_HIGH"
        return with_direction(result, state, "BUY", "confirmed new 100-day high agrees with the bullish 50/100 EMA filter")
    if trend == "down" and extreme == "new 100 day low":
        result["clenow_core_assessment"] = "SELL_100_DAY_LOW"
        return with_direction(result, state, "SELL", "confirmed new 100-day low agrees with the bearish 50/100 EMA filter")
    result["clenow_core_assessment"] = "EXTREME_DIRECTION_MISMATCH"
    result["view"] = "WAIT"
    result["reasons"] = ["the breakout extreme conflicts with the observed trend"]
    return result
