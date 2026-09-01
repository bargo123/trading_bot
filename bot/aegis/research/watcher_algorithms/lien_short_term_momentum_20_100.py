"""Kathy Lien's 20-100 short-term momentum checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "lien_short_term_momentum_20_100"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_20_ema",
    "lien_100_sma",
    "lien_price_cross_distance_pips",
    "lien_macd_direction",
    "lien_macd_turn_age_candles",
    "lien_pre_cross_position",
    "lien_break_candle_low_or_high_valid",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "lien_data_provenance")):
        missing.append("lien_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    ema20 = number(first(state, "lien_20_ema"))
    sma100 = number(first(state, "lien_100_sma"))
    cross = number(first(state, "lien_price_cross_distance_pips"))
    age = number(first(state, "lien_macd_turn_age_candles"))
    if any(value is None for value in (ema20, sma100, cross, age)):
        result["reasons"] = ["moving averages, cross distance, and MACD age must be finite observations"]
        return result
    if age < 0 or age > 5:
        result["reasons"] = ["the MACD turn is older than the five-candle entry window"]
        return result
    if first(state, "lien_break_candle_low_or_high_valid") is not True:
        result["reasons"] = ["the moving-average break candle has no valid structural stop reference"]
        return result
    candidate_side = side(state)
    pre_cross = normalized_status(first(state, "lien_pre_cross_position"))
    macd = normalized_status(first(state, "lien_macd_direction"))
    signal = None
    if candidate_side == "BUY" and pre_cross == "below both" and ema20 > sma100 and cross >= 15 and macd == "positive":
        signal = "BUY"
    elif candidate_side == "SELL" and pre_cross == "above both" and ema20 < sma100 and cross <= -15 and macd == "negative":
        signal = "SELL"
    if signal is None:
        result["reasons"] = ["the 20-EMA/100-SMA cross, prior location, MACD turn, and side do not align"]
        return result
    return with_direction(result, state, signal, "fresh MACD turn confirms a 15-pip 20-100 momentum cross")
