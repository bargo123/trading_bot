"""The Ultimate Forex Trading System's Abandoned Baby EMA(5) perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_abandoned_baby_ema5"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_candle_type",
    "ultimate_timeframe",
    "ultimate_ema_period",
    "ultimate_ema_value",
    "ultimate_reversal_close",
    "ultimate_previous_bar_range",
    "ultimate_new_bar_open_alert",
    "ultimate_data_provenance",
)


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
    candle = normalized_status(first(state, "ultimate_candle_type"))
    timeframe = normalized_status(first(state, "ultimate_timeframe"))
    ema_period = number(first(state, "ultimate_ema_period"))
    ema = number(first(state, "ultimate_ema_value"))
    close = number(first(state, "ultimate_reversal_close"))
    previous_range = number(first(state, "ultimate_previous_bar_range"))
    accepted_candles = {"doji", "morning star", "evening star", "upper shadow", "lower shadow", "abandoned baby"}
    if candle not in accepted_candles:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed reversal candle is not an Abandoned Baby-style candle"]
        return result
    if timeframe not in {"daily", "weekly"} or ema_period != 5:
        result["view"] = "WAIT"
        result["reasons"] = ["the source rule requires EMA(5) on a daily or weekly chart"]
        return result
    if any(value is None for value in (ema, close, previous_range)) or ema <= 0 or previous_range <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["EMA, reversal close, and prior-bar range must be valid observations"]
        return result
    if not _truthy(first(state, "ultimate_new_bar_open_alert")):
        result["view"] = "WAIT"
        result["reasons"] = ["the source entry alert occurs at the opening of the new bar"]
        return result
    distance = abs(close - ema)
    if distance < previous_range or close == ema:
        result["view"] = "WAIT"
        result["reasons"] = ["the close-to-EMA deviation is smaller than the previous bar range"]
        return result
    signal = "BUY" if close < ema else "SELL"
    result["ultimate_ema5_deviation"] = close - ema
    result["ultimate_mean_reversion_target"] = ema
    return with_direction(result, state, signal, "the validated Abandoned Baby deviation points back toward EMA(5)")
