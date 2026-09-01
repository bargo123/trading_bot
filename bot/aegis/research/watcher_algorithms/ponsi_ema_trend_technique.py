"""Ponsi FX trend technique: proper order, EMA support, and pullback entry."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ponsi_ema_trend_technique"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_trend_direction",
    "ponsi_ma10",
    "ponsi_ma20",
    "ponsi_ma50",
    "ponsi_ma200",
    "ponsi_ema10_support_bars",
    "ponsi_price_at_ema10",
    "ponsi_pullback_confirmation",
    "ponsi_stop_buffer_atr",
    "ponsi_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present"}


def _direction(value) -> str | None:
    value = normalized_status(value)
    if value in {"buy", "long", "up", "bull", "bullish", "uptrend"}:
        return "BUY"
    if value in {"sell", "short", "down", "bear", "bearish", "downtrend"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("proper_order_ema_pullback",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not explicitly_observed(first(state, "ponsi_data_provenance"), accepted=("observed", "measured", "timestamped", "journal")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["ponsi_data_provenance"]
        result["reasons"] = ["the EMA technique requires observed timestamped trend evidence"]
        return result
    trend = _direction(first(state, "ponsi_trend_direction"))
    ma10, ma20, ma50, ma200 = (number(first(state, key)) for key in ("ponsi_ma10", "ponsi_ma20", "ponsi_ma50", "ponsi_ma200"))
    support_bars = number(first(state, "ponsi_ema10_support_bars"))
    stop_buffer = number(first(state, "ponsi_stop_buffer_atr"))
    if trend is None or None in {ma10, ma20, ma50, ma200, support_bars, stop_buffer} or min(ma10, ma20, ma50, ma200) <= 0 or support_bars < 0 or stop_buffer <= 0:
        result["view"] = "WAIT"
        result["ponsi_ema_technique_assessment"] = "INVALID_INPUTS"
        result["reasons"] = ["proper-order EMA, support-duration, and ATR-buffer inputs are incomplete or invalid"]
        return result
    proper_order = (
        trend == "BUY" and ma10 > ma20 > ma50 > ma200
    ) or (
        trend == "SELL" and ma200 > ma50 > ma20 > ma10
    )
    if not proper_order:
        result["view"] = "WAIT"
        result["ponsi_ema_technique_assessment"] = "PROPER_ORDER_MISSING"
        result["reasons"] = ["10, 20, 50, and 200 period averages are not in the source-defined directional order"]
        return result
    if support_bars < 10:
        result["view"] = "WAIT"
        result["ponsi_ema_technique_assessment"] = "EMA_SUPPORT_NOT_ESTABLISHED"
        result["reasons"] = ["the source requires at least 10 observed candles holding the 10-period EMA role"]
        return result
    if not _truth(first(state, "ponsi_price_at_ema10")) or not (explicitly_confirmed(first(state, "ponsi_pullback_confirmation")) or _truth(first(state, "ponsi_pullback_confirmation"))):
        result["view"] = "WAIT"
        result["ponsi_ema_technique_assessment"] = "PULLBACK_NOT_CONFIRMED"
        result["reasons"] = ["price has not confirmed the source-defined pullback to the 10-period EMA"]
        return result
    if abs(stop_buffer - 0.50) > 1e-9:
        result["view"] = "WAIT"
        result["ponsi_ema_technique_assessment"] = "ATR_STOP_BUFFER_MISMATCH"
        result["reasons"] = ["the source example places the initial stop one-half ATR beyond the 10-period EMA"]
        return result
    result["ponsi_ema_technique_assessment"] = "CONFIRMED_PULLBACK"
    result["ponsi_stop_buffer_atr"] = stop_buffer
    return with_direction(result, state, trend, "proper-order averages, established 10-period EMA support, and a confirmed EMA pullback are observed")
