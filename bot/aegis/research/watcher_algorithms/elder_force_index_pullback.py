"""Alexander Elder's 2-day Force Index pullback entry perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "elder_force_index_pullback"
SOURCES = ("Alexander Elder — The New Trading for a Living",)
KEYS = (
    "elder_long_term_trend",
    "elder_force_index_ema_period",
    "elder_force_index_ema_value",
    "elder_entry_trigger",
    "elder_latest_bar_high",
    "elder_latest_bar_low",
    "elder_entry_price",
    "elder_stop_price",
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
    trend = normalized_status(first(state, "elder_long_term_trend"))
    period = number(first(state, "elder_force_index_ema_period"))
    force = number(first(state, "elder_force_index_ema_value"))
    trigger = normalized_status(first(state, "elder_entry_trigger"))
    high = number(first(state, "elder_latest_bar_high"))
    low = number(first(state, "elder_latest_bar_low"))
    entry = number(first(state, "elder_entry_price"))
    stop = number(first(state, "elder_stop_price"))
    if period != 2 or any(value is None for value in (force, high, low, entry, stop)) or high <= low:
        result["view"] = "WAIT"
        result["reasons"] = ["the 2-day Force Index and latest-bar geometry are not valid"]
        return result
    if trend in {"up", "uptrend", "bull", "bullish"} and force < 0 and trigger == "above high" and entry > high and stop < low:
        signal = "BUY"
    elif trend in {"down", "downtrend", "bear", "bearish"} and force > 0 and trigger == "below low" and entry < low and stop > high:
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["trend, Force Index pullback, trigger, or structural stop do not align"]
        return result
    result["elder_force_index_period"] = period
    result["elder_force_index_geometry"] = {"entry": entry, "stop": stop, "bar_high": high, "bar_low": low}
    return with_direction(result, state, signal, "the 2-day Force Index pullback is paired with a source-compliant breakout trigger")
