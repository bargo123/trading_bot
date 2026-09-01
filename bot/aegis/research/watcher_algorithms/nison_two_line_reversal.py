"""Nison two-line reversal patterns with explicit candle geometry."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_two_line_reversal"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_two_line_pattern",
    "nison_two_line_prior_trend",
    "nison_two_line_first_color",
    "nison_two_line_second_color",
    "nison_two_line_open_relation",
    "nison_two_line_close_relation",
    "nison_two_line_body_engulfed",
    "nison_two_line_geometry_confirmed",
    "nison_two_line_followthrough",
    "nison_data_provenance",
)


def _down_followthrough(value) -> bool:
    return normalized_status(value) in {"down", "bearish", "lower close", "bearish confirmed", "confirmed down"}


def _up_followthrough(value) -> bool:
    return normalized_status(value) in {"up", "bullish", "higher close", "bullish confirmed", "confirmed up"}


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_two_line_geometry_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["two-line candle geometry is not confirmed"]
        return result
    pattern = normalized_status(first(state, "nison_two_line_pattern"))
    trend = normalized_status(first(state, "nison_two_line_prior_trend"))
    first_color = normalized_status(first(state, "nison_two_line_first_color"))
    second_color = normalized_status(first(state, "nison_two_line_second_color"))
    open_relation = normalized_status(first(state, "nison_two_line_open_relation"))
    close_relation = normalized_status(first(state, "nison_two_line_close_relation"))
    engulfed = volman_truth(first(state, "nison_two_line_body_engulfed"))
    followthrough = first(state, "nison_two_line_followthrough")

    if pattern == "dark cloud cover":
        if trend not in {"up", "uptrend", "rally", "rising"} or first_color != "white" or second_color != "black":
            result["view"] = "WAIT"
            result["reasons"] = ["dark cloud cover requires an uptrend followed by white then black candles"]
            return result
        if open_relation not in {"above prior high", "above prior close"}:
            result["view"] = "WAIT"
            result["reasons"] = ["dark cloud cover second candle did not open above the prior candle"]
            return result
        if close_relation == "below midpoint":
            result["nison_two_line_assessment"] = "DARK_CLOUD_IDEAL"
            return with_direction(result, state, "SELL", "black candle closed below the prior white midpoint")
        if close_relation == "inside body not midpoint" and _down_followthrough(followthrough):
            result["nison_two_line_assessment"] = "DARK_CLOUD_INCOMPLETE_CONFIRMED"
            return with_direction(result, state, "SELL", "incomplete dark cloud received later weakness confirmation")
        result["view"] = "WAIT"
        result["reasons"] = ["dark cloud cover needs a midpoint close or subsequent weakness confirmation"]
        return result

    if pattern == "piercing pattern":
        if trend not in {"down", "downtrend", "decline", "falling"} or first_color != "black" or second_color != "white":
            result["view"] = "WAIT"
            result["reasons"] = ["piercing pattern requires a downtrend followed by black then white candles"]
            return result
        if open_relation not in {"below prior low", "below prior close"}:
            result["view"] = "WAIT"
            result["reasons"] = ["piercing pattern second candle did not open below the prior candle"]
            return result
        if close_relation == "above midpoint":
            result["nison_two_line_assessment"] = "PIERCING_IDEAL"
            return with_direction(result, state, "BUY", "white candle closed above the prior black midpoint")
        if close_relation == "inside body below midpoint" and _up_followthrough(followthrough):
            result["nison_two_line_assessment"] = "PIERCING_INCOMPLETE_CONFIRMED"
            return with_direction(result, state, "BUY", "incomplete piercing pattern received later strength confirmation")
        result["view"] = "WAIT"
        result["reasons"] = ["piercing pattern needs a midpoint close or subsequent strength confirmation"]
        return result

    if pattern == "bullish engulfing":
        valid = trend in {"down", "downtrend", "decline", "falling"} and first_color == "black" and second_color == "white" and engulfed
        if valid:
            result["nison_two_line_assessment"] = "BULLISH_ENGULFING"
            return with_direction(result, state, "BUY", "white real body engulfed the prior black real body")
    if pattern == "bearish engulfing":
        valid = trend in {"up", "uptrend", "rally", "rising"} and first_color == "white" and second_color == "black" and engulfed
        if valid:
            result["nison_two_line_assessment"] = "BEARISH_ENGULFING"
            return with_direction(result, state, "SELL", "black real body engulfed the prior white real body")
    result["view"] = "WAIT"
    result["reasons"] = ["two-line pattern, context, and candle geometry do not agree"]
    return result
