"""Closed-bar price-action and candlestick algorithm."""
from __future__ import annotations
from ._common import absent, base, direction, explicitly_confirmed, first, strings, values, with_direction

ALGORITHM_ID = "price_action_candles"
SOURCES = ("Al Brooks — Reading Price Charts Bar by Bar", "Steve Nison — Japanese Candlestick Charting Techniques", "John F. Carter — Mastering the Trade")
KEYS = ("candle", "candle_pattern", "signal_bar", "bar_pattern", "reversal_bar", "doji", "closed_bar", "candle_body", "candle_upper_wick", "candle_lower_wick", "candle_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("candle_or_signal_bar",))
    text = " ".join(str(value).lower() for _, value in found)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("doji", "inside", "unclear")):
        result["view"] = "WAIT"
        result["reasons"] = ["signal bar does not establish directional clarity"]
        return result
    if "bullish_hammer" in text:
        return with_direction(result, state, "BUY", "closed quote-bar shape is a bullish hammer; continuation/reversal is a research hypothesis")
    if "bearish_shooting_star" in text:
        return with_direction(result, state, "SELL", "closed quote-bar shape is a bearish shooting star; continuation/reversal is a research hypothesis")
    signal = direction(text)
    if "reversal" in text and signal:
        return with_direction(result, state, signal, "closed-bar reversal direction is recorded")
    if first(state, "closed_bar") is not True and not explicitly_confirmed(text) and "closed" not in text:
        result["view"] = "WAIT"
        result["reasons"] = ["signal-bar confirmation state is not recorded"]
        return result
    return with_direction(result, state, signal, "price-action direction is recorded on a closed or confirmed bar")
