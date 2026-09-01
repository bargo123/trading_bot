"""John Carter's HOLP/LOHP trend-reversal confirmation study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_holp_lohp"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_holp_mode",
    "carter_trend_direction",
    "carter_extreme_lookback",
    "carter_extreme_bar_high",
    "carter_extreme_bar_low",
    "carter_latest_close",
    "carter_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    mode = normalized_status(first(state, "carter_holp_mode")).upper()
    trend = normalized_status(first(state, "carter_trend_direction"))
    lookback = number(first(state, "carter_extreme_lookback"))
    extreme_high = number(first(state, "carter_extreme_bar_high"))
    extreme_low = number(first(state, "carter_extreme_bar_low"))
    latest_close = number(first(state, "carter_latest_close"))
    if mode not in {"HOLP", "LOHP"} or trend not in {"up", "uptrend", "bull", "bullish", "down", "downtrend", "bear", "bearish"}:
        result["view"] = "WAIT"
        result["reasons"] = ["HOLP/LOHP requires a classified trend and explicit mode"]
        return result
    if lookback is None or lookback < 17:
        result["view"] = "WAIT"
        result["reasons"] = ["the source requires a definitive roughly 20-period extreme, with 17 as the lower rule of thumb"]
        return result
    if any(value is None for value in (extreme_high, extreme_low, latest_close)) or extreme_high <= extreme_low:
        result["view"] = "WAIT"
        result["reasons"] = ["the extreme bar geometry is invalid"]
        return result
    if mode == "LOHP" and trend in {"up", "uptrend", "bull", "bullish"}:
        if latest_close >= extreme_low:
            result["view"] = "WAIT"
            result["reasons"] = ["LOHP needs a close below the low of the high bar"]
            return result
        signal = "SELL"
        stop = extreme_high
    elif mode == "HOLP" and trend in {"down", "downtrend", "bear", "bearish"}:
        if latest_close <= extreme_high:
            result["view"] = "WAIT"
            result["reasons"] = ["HOLP needs a close above the high of the low bar"]
            return result
        signal = "BUY"
        stop = extreme_low
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["HOLP buys the high of a low period and LOHP sells the low of a high period"]
        return result
    result["carter_initial_stop"] = stop
    result["carter_extreme_lookback"] = lookback
    return with_direction(result, state, signal, "the trend extreme closed through its reversal trigger")
