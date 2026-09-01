"""Nison hammer/hanging-man context and confirmation perspective.

The source distinguishes the same candle shape by the preceding trend: a
hammer follows a meaningful decline, while a hanging man follows a rally and
needs bearish confirmation.  This is a research-only observation; it never
authorizes an order.
"""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, with_direction

ALGORITHM_ID = "nison_hammer_hanging_man"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_single_line_type",
    "nison_single_line_trend",
    "nison_single_line_shape",
    "nison_single_line_confirmation",
    "nison_data_provenance",
)


def _confirmed_bearish(value) -> bool:
    if value is True:
        return True
    return normalized_status(value) in {
        "bearish confirmed",
        "confirmed bearish",
        "down confirmed",
        "confirmed down",
        "lower close",
    }


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candle_type = normalized_status(first(state, "nison_single_line_type"))
    trend = normalized_status(first(state, "nison_single_line_trend"))
    shape = normalized_status(first(state, "nison_single_line_shape"))
    if shape != "long lower shadow small body near high":
        result["view"] = "WAIT"
        result["reasons"] = ["hammer/hanging-man lower-shadow shape is not confirmed"]
        return result
    if candle_type == "hammer":
        if trend not in {"down", "downtrend", "decline", "falling"}:
            result["view"] = "WAIT"
            result["reasons"] = ["a hammer requires a preceding meaningful decline"]
            return result
        result["nison_single_line_assessment"] = "HAMMER_AFTER_DOWNTREND"
        return with_direction(result, state, "BUY", "hammer shape followed a downtrend")
    if candle_type == "hanging man":
        if trend not in {"up", "uptrend", "rally", "rising"}:
            result["view"] = "WAIT"
            result["reasons"] = ["a hanging man requires a preceding rally"]
            return result
        if not _confirmed_bearish(first(state, "nison_single_line_confirmation")):
            result["view"] = "WAIT"
            result["reasons"] = ["hanging man requires a bearish next-session confirmation"]
            return result
        result["nison_single_line_assessment"] = "HANGING_MAN_CONFIRMED"
        return with_direction(result, state, "SELL", "hanging man followed an uptrend and was confirmed bearishly")
    result["view"] = "WAIT"
    result["reasons"] = ["single-line type is not hammer or hanging man"]
    return result
