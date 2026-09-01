"""Named Japanese candlestick reversal and continuation patterns."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, strings, values, with_direction

ALGORITHM_ID = "candlestick_patterns"
SOURCES = (
    "Steve Nison — Japanese Candlestick Charting Techniques",
    "Al Brooks — Reading Price Charts Bar by Bar",
)
KEYS = ("candlestick_pattern", "closed_bar", "candlestick_confirmation", "candle_data_provenance")

_BUY = {"hammer", "bullish_engulfing", "morning_star", "piercing_line", "three_white_soldiers", "bullish_harami"}
_SELL = {"shooting_star", "bearish_engulfing", "evening_star", "dark_cloud_cover", "three_black_crows", "bearish_harami"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("named_closed_candlestick_pattern",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pattern = str(first(state, "candlestick_pattern") or "").strip().lower().replace(" ", "_")
    closed = first(state, "closed_bar") is True
    confirmed = explicitly_confirmed(first(state, "candlestick_confirmation"))
    if not closed and not confirmed:
        result["view"] = "WAIT"
        result["reasons"] = ["candlestick pattern is not on a closed or explicitly confirmed bar"]
        return result
    if pattern in {"doji", "inside_bar", "indecision"}:
        result["view"] = "WAIT"
        result["reasons"] = ["named candle expresses indecision rather than a directional edge"]
        return result
    signal = "BUY" if pattern in _BUY else "SELL" if pattern in _SELL else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["named candlestick pattern is not in the supported directional set"]
        return result
    return with_direction(result, state, signal, f"closed named candlestick pattern: {pattern}")
