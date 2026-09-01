"""Price-versus-momentum divergence algorithm."""
from __future__ import annotations

from ._common import absent, base, strings, values, with_direction

ALGORITHM_ID = "divergence"
SOURCES = (
    "Alexander Elder — The New Trading for a Living",
    "Steve Nison — Japanese Candlestick Charting Techniques",
    "John F. Carter — Mastering the Trade",
    "Adam Grimes — The Art and Science of Technical Analysis",
)
KEYS = ("divergence", "price_oscillator_divergence", "momentum_divergence", "rsi_divergence", "macd_divergence", "hidden_divergence")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("price_momentum_divergence",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("failed", "invalid", "unclear")):
        result["view"] = "WAIT"
        result["reasons"] = ["divergence evidence is explicitly failed or unclear"]
        return result
    if any(token in text for token in ("bullish", "positive", "hidden bull", "higher low")):
        return with_direction(result, state, "BUY", "price and oscillator divergence favors an upside reversal or continuation")
    if any(token in text for token in ("bearish", "negative", "hidden bear", "lower high")):
        return with_direction(result, state, "SELL", "price and oscillator divergence favors a downside reversal or continuation")
    result["view"] = "WAIT"
    result["reasons"] = ["divergence field is present without a directional classification"]
    return result
