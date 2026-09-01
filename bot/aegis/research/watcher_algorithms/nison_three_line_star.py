"""Nison morning/evening star patterns with three completed candle roles."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_three_line_star"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_three_line_pattern",
    "nison_three_line_prior_trend",
    "nison_three_line_first_color",
    "nison_three_line_middle_body",
    "nison_three_line_third_color",
    "nison_three_line_penetration",
    "nison_three_line_bodies_separated",
    "nison_three_line_closed",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_three_line_closed")) or not volman_truth(first(state, "nison_three_line_bodies_separated")):
        result["view"] = "WAIT"
        result["reasons"] = ["three-line star must be observed on completed, separated candle bodies"]
        return result
    pattern = normalized_status(first(state, "nison_three_line_pattern"))
    trend = normalized_status(first(state, "nison_three_line_prior_trend"))
    first_color = normalized_status(first(state, "nison_three_line_first_color"))
    middle = normalized_status(first(state, "nison_three_line_middle_body"))
    third_color = normalized_status(first(state, "nison_three_line_third_color"))
    penetration = normalized_status(first(state, "nison_three_line_penetration"))
    if middle not in {"small body", "doji"} or penetration != "well into first body":
        result["view"] = "WAIT"
        result["reasons"] = ["middle star and third-candle penetration are not confirmed"]
        return result
    if pattern in {"morning star", "morning doji star"}:
        valid = trend in {"down", "downtrend", "decline", "falling"} and first_color == "long black" and third_color == "long white"
        if valid:
            result["nison_three_line_assessment"] = "MORNING_STAR_CONFIRMED"
            return with_direction(result, state, "BUY", "long white third candle penetrated the first black body after a decline")
    if pattern in {"evening star", "evening doji star"}:
        valid = trend in {"up", "uptrend", "rally", "rising"} and first_color == "long white" and third_color == "long black"
        if valid:
            result["nison_three_line_assessment"] = "EVENING_STAR_CONFIRMED"
            return with_direction(result, state, "SELL", "long black third candle penetrated the first white body after a rally")
    result["view"] = "WAIT"
    result["reasons"] = ["three-line star pattern, trend, and candle roles do not agree"]
    return result
