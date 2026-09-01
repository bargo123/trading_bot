"""Moving-average slope, cross, and trend-context algorithm."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "moving_average_context"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Alexander Elder — The New Trading for a Living",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = ("ma_fast", "ma_slow", "ema_fast", "ema_slow", "sma_fast", "sma_slow", "ma_cross", "ema_cross", "ma_slope", "ema_fast_slope", "moving_average_state")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("moving_average_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, *KEYS)
    fast = number(first(state, "ma_fast", "ema_fast", "sma_fast"))
    slow = number(first(state, "ma_slow", "ema_slow", "sma_slow"))
    signal = None
    if fast is not None and slow is not None and fast != slow:
        signal = "BUY" if fast > slow else "SELL"
    if any(token in text for token in ("cross up", "bullish cross", "slope up", "rising")):
        signal = "BUY"
    elif any(token in text for token in ("cross down", "bearish cross", "slope down", "falling")):
        signal = "SELL"
    if signal:
        return with_direction(result, state, signal, "moving-average relationship or slope gives a directional context")
    result["view"] = "WAIT"
    result["reasons"] = ["moving averages are present without a consistent cross, slope, or ordering"]
    return result
