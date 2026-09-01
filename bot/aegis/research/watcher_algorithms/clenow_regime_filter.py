"""Clenow's long-horizon EMA trend filter as a Watcher perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "clenow_regime_filter"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_fast_ema",
    "clenow_slow_ema",
    "clenow_trend_filter",
    "clenow_regime_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "clenow_regime_data_provenance"),
        accepted=("observed", "timestamped"),
    ):
        missing.append("clenow_regime_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    fast = number(first(state, "clenow_fast_ema"))
    slow = number(first(state, "clenow_slow_ema"))
    if fast is None or slow is None:
        result["clenow_regime_assessment"] = "INVALID_EMA_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["EMA values must be finite numbers"]
        return result

    result["clenow_fast_period"] = 50
    result["clenow_slow_period"] = 100
    result["clenow_ema_spread"] = fast - slow
    if fast == slow:
        result["clenow_regime_assessment"] = "NON_TRENDING"
        result["clenow_regime_direction"] = None
        result["view"] = "WAIT"
        result["reasons"] = ["the 50-day and 100-day EMAs are not directional"]
        return result

    computed = "up" if fast > slow else "down"
    declared = normalized_status(first(state, "clenow_trend_filter"))
    if declared != computed:
        result["clenow_regime_assessment"] = "FILTER_DISAGREEMENT"
        result["clenow_regime_direction"] = "BUY" if computed == "up" else "SELL"
        result["view"] = "WAIT"
        result["reasons"] = ["declared trend filter disagrees with the observed EMA ordering"]
        return result

    signal = "BUY" if computed == "up" else "SELL"
    result["clenow_regime_assessment"] = "BULLISH_TREND" if signal == "BUY" else "BEARISH_TREND"
    result["clenow_regime_direction"] = signal
    return with_direction(
        result,
        state,
        signal,
        "the observed 50-day EMA is on the corresponding side of the 100-day EMA",
    )
