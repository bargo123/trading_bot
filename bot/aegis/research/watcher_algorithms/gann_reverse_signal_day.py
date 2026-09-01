"""W. D. Gann's reverse-signal-day price/action perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "gann_reverse_signal_day"
SOURCES = ("W. D. Gann — How to Make Profits in Commodities",)
KEYS = (
    "gann_market_trend",
    "gann_extreme_break",
    "gann_close_location",
    "gann_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "gann_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("gann_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "gann_market_trend"))
    close = normalized_status(first(state, "gann_close_location"))
    if not _truthy(first(state, "gann_extreme_break")):
        result["view"] = "WAIT"
        result["reasons"] = ["the current day has not broken the prior extreme"]
        return result
    if trend in {"declining", "down", "bear", "bearish"} and close == "near high":
        signal = "BUY"
    elif trend in {"advancing", "up", "bull", "bullish"} and close == "near low":
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the close does not form the source's reverse signal day against the prior trend"]
        return result
    return with_direction(result, state, signal, "the day broke the old extreme and reversed to close near the opposite end")
