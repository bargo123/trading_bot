"""Clenow's volatility-scaled buy-the-dip counter-trend model."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "clenow_countertrend_pullback"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_countertrend_fast_ema40",
    "clenow_countertrend_slow_ema80",
    "clenow_countertrend_recent_high_20",
    "clenow_countertrend_current_price",
    "clenow_countertrend_atr",
    "clenow_countertrend_data_provenance",
)


def _missing(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "clenow_countertrend_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("clenow_countertrend_data_provenance")
    return list(dict.fromkeys(missing))


def evaluate(state):
    missing = _missing(state)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    fast = number(first(state, "clenow_countertrend_fast_ema40"))
    slow = number(first(state, "clenow_countertrend_slow_ema80"))
    recent_high = number(first(state, "clenow_countertrend_recent_high_20"))
    current = number(first(state, "clenow_countertrend_current_price"))
    atr = number(first(state, "clenow_countertrend_atr"))
    candidate_side = side(state)
    if any(value is None for value in (fast, slow, recent_high, current, atr)) or atr <= 0:
        result["reasons"] = ["40/80 EMA, 20-day high, current price, and ATR must be finite with positive ATR"]
        return result
    if current > recent_high:
        result["reasons"] = ["current price is above the observed 20-day high, so no pullback exists"]
        return result
    pullback_multiple = (recent_high - current) / atr
    result["clenow_pullback_atr_multiple"] = pullback_multiple
    if fast <= slow:
        result["reasons"] = ["the 40-day EMA is not above the 80-day EMA bull-market filter"]
        return result
    if candidate_side != "BUY":
        result["reasons"] = ["this source counter-trend demonstration buys bull-market dips and does not authorize a short mirror"]
        return result
    if pullback_multiple < 3.0:
        result["reasons"] = ["the pullback has not reached the source's three-ATR trigger"]
        return result
    result["clenow_countertrend_entry"] = True
    return with_direction(result, state, "BUY", "bull-market 40/80 EMA alignment and a three-ATR pullback agree")
