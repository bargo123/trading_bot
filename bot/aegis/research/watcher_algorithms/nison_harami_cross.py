"""Nison harami-cross (long body followed by a contained doji) perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_harami_cross"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_harami_cross_trend",
    "nison_harami_cross_first_color",
    "nison_harami_cross_second_location",
    "nison_harami_cross_second_range_inside",
    "nison_harami_cross_follow_through",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "nison_harami_cross_trend"))
    first_color = normalized_status(first(state, "nison_harami_cross_first_color"))
    location = normalized_status(first(state, "nison_harami_cross_second_location"))
    follow_through = normalized_status(first(state, "nison_harami_cross_follow_through"))
    if location not in {"middle", "center", "middle of first body"} or not volman_truth(first(state, "nison_harami_cross_second_range_inside")):
        result["view"] = "WAIT"
        result["reasons"] = ["harami cross requires a centered doji contained by the first real body"]
        return result
    if trend in {"down", "downtrend", "decline", "falling"} and first_color == "long white":
        if follow_through in {"below harami low", "close below harami low", "down"}:
            result["nison_harami_cross_assessment"] = "BEARISH_HARAMI_CROSS_CONTINUATION"
            return with_direction(result, state, "SELL", "downtrend follow-through broke the harami-cross low")
        result["nison_harami_cross_assessment"] = "BULLISH_HARAMI_CROSS_REVERSAL"
        return with_direction(result, state, "BUY", "a centered contained doji followed a decline after a long white body")
    if trend in {"up", "uptrend", "rally", "rising"} and first_color == "long black":
        if follow_through in {"above harami high", "close above harami high", "up"}:
            result["nison_harami_cross_assessment"] = "BULLISH_HARAMI_CROSS_CONTINUATION"
            return with_direction(result, state, "BUY", "uptrend follow-through broke the harami-cross high")
        result["nison_harami_cross_assessment"] = "BEARISH_HARAMI_CROSS_REVERSAL"
        return with_direction(result, state, "SELL", "a centered contained doji followed a rally after a long black body")
    result["view"] = "WAIT"
    result["reasons"] = ["harami-cross trend and first-body color do not agree"]
    return result
