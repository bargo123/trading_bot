"""Schwager's long-term moving-average reaction entry perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_long_ma_reaction"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_long_ma_trend",
    "schwager_long_ma_period",
    "schwager_long_ma_value",
    "schwager_long_ma_price",
    "schwager_long_ma_reaction_confirmed",
    "schwager_long_ma_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "moving average" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_long_ma_data_provenance")):
        missing.append("schwager_long_ma_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "schwager_long_ma_trend"))
    period = number(first(state, "schwager_long_ma_period"))
    moving_average = number(first(state, "schwager_long_ma_value"))
    price = number(first(state, "schwager_long_ma_price"))
    if trend not in {"up", "uptrend", "down", "downtrend"} or None in {period, moving_average, price} or period < 20 or moving_average <= 0 or price <= 0:
        result["schwager_long_ma_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["a long-term trend, period of at least 20, and finite positive price/average are required"]
        return result
    if not _truth(first(state, "schwager_long_ma_reaction_confirmed")):
        result["schwager_long_ma_assessment"] = "REACTION_UNCONFIRMED"
        result["reasons"] = ["price has not produced a confirmed reaction at the long moving average"]
        return result
    if trend in {"up", "uptrend"} and price <= moving_average:
        result["schwager_long_ma_assessment"] = "UPTREND_PULLBACK_TO_LONG_MA"
        return with_direction(result, state, "BUY", "price pulled back to or below the long moving average while the trend remained up")
    if trend in {"down", "downtrend"} and price >= moving_average:
        result["schwager_long_ma_assessment"] = "DOWNTREND_RALLY_TO_LONG_MA"
        return with_direction(result, state, "SELL", "price rallied to or above the long moving average while the trend remained down")
    result["schwager_long_ma_assessment"] = "PRICE_NOT_AT_LONG_MA"
    result["reasons"] = ["the price has not reacted to the long moving average from the trend-consistent side"]
    return result
