"""Alexander Elder's long-tide, counter-trend-wave Triple Screen study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "elder_triple_screen"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = (
    "elder_long_term_trend",
    "elder_intermediate_wave",
    "elder_timeframe_ratio",
    "elder_oscillator_signal",
    "elder_entry_technique",
    "elder_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "elder_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("elder_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    long_trend = normalized_status(first(state, "elder_long_term_trend"))
    wave = normalized_status(first(state, "elder_intermediate_wave"))
    oscillator = normalized_status(first(state, "elder_oscillator_signal"))
    entry = normalized_status(first(state, "elder_entry_technique"))
    ratio = number(first(state, "elder_timeframe_ratio"))
    if ratio is None or ratio < 5:
        result["view"] = "WAIT"
        result["reasons"] = ["the long and intermediate screens are not separated by the source's factor of five"]
        return result
    if long_trend in {"up", "uptrend", "bull", "bullish"}:
        if wave not in {"decline", "down", "downtrend", "bear", "bearish"} or oscillator not in {"below zero", "buy zone", "oversold", "declining"} or entry not in {"upside breakout", "ema penetration"}:
            result["view"] = "WAIT"
            result["reasons"] = ["an up-tide Triple Screen requires a counter-trend decline and buy trigger"]
            return result
        signal = "BUY"
    elif long_trend in {"down", "downtrend", "bear", "bearish"}:
        if wave not in {"rally", "up", "uptrend", "bull", "bullish"} or oscillator not in {"above zero", "sell zone", "overbought", "rising"} or entry not in {"downside breakout", "ema penetration"}:
            result["view"] = "WAIT"
            result["reasons"] = ["a down-tide Triple Screen requires a counter-trend rally and sell trigger"]
            return result
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the long-term market tide is not classified"]
        return result
    result["elder_screen_ratio"] = ratio
    result["elder_screen_action"] = signal
    return with_direction(result, state, signal, "long-term tide, counter-trend wave, oscillator, and entry screen align")
