"""Jack Schwager's repeated-close false trend-line breakout study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_false_trend_breakout"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_trend_direction",
    "schwager_trend_line_break_direction",
    "schwager_counter_close_count",
    "schwager_required_counter_closes",
    "schwager_false_breakout_confirmed",
    "schwager_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upside", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downside", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "schwager_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("schwager_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = _direction(first(state, "schwager_trend_direction"))
    breakout = _direction(first(state, "schwager_trend_line_break_direction"))
    closes = number(first(state, "schwager_counter_close_count"))
    required = number(first(state, "schwager_required_counter_closes"))
    if trend is None or breakout is None or closes is None or required is None or required < 1 or closes < 0:
        result["view"] = "WAIT"
        result["schwager_false_trend_assessment"] = "FALSE_TREND_INPUT_INVALID"
        result["reasons"] = ["trend, breakout, and repeated-close counts must be finite observed values"]
        return result
    if not _truthy(first(state, "schwager_false_breakout_confirmed")):
        result["view"] = "WAIT"
        result["schwager_false_trend_assessment"] = "FALSE_BREAK_NOT_CONFIRMED"
        result["reasons"] = ["the false trend-line breakout has not been explicitly confirmed"]
        return result
    if closes < required:
        result["view"] = "WAIT"
        result["schwager_false_trend_assessment"] = "COUNTER_CLOSES_INSUFFICIENT"
        result["reasons"] = ["the source's required number of closes beyond the trend line is not present"]
        return result
    if trend == "SELL" and breakout == "BUY":
        signal = "SELL"
        assessment = "FALSE_UPSIDE_BREAK"
    elif trend == "BUY" and breakout == "SELL":
        signal = "BUY"
        assessment = "FALSE_DOWNSIDE_BREAK"
    else:
        result["view"] = "WAIT"
        result["schwager_false_trend_assessment"] = "TREND_BREAK_COMBINATION_INVALID"
        result["reasons"] = ["the false breakout must penetrate opposite the prevailing trend and then close back through the line"]
        return result
    result["schwager_false_trend_assessment"] = assessment
    result["schwager_counter_close_count"] = closes
    return with_direction(result, state, signal, "repeated closes confirm a false trend-line breakout")
