"""Nison harami reversal/transition perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_harami"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_harami_trend",
    "nison_harami_first_color",
    "nison_harami_second_body",
    "nison_harami_second_location",
    "nison_harami_second_range_inside",
    "nison_harami_follow_through",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "nison_harami_trend"))
    first_color = normalized_status(first(state, "nison_harami_first_color"))
    second_body = normalized_status(first(state, "nison_harami_second_body"))
    location = normalized_status(first(state, "nison_harami_second_location"))
    follow_through = normalized_status(first(state, "nison_harami_follow_through"))
    if second_body not in {"small body", "doji"} or not volman_truth(first(state, "nison_harami_second_range_inside")):
        result["view"] = "WAIT"
        result["reasons"] = ["harami requires a small/doji second body contained by the prior real body"]
        return result
    if location not in {"middle", "center", "middle of first body"}:
        result["nison_harami_assessment"] = "LOW_OR_HIGH_PRICE_TRANSITION"
        result["view"] = "WAIT"
        result["reasons"] = ["low/high-price harami is treated as a transition or consolidation warning"]
        return result
    if trend in {"down", "downtrend", "decline", "falling"}:
        if follow_through in {"below harami low", "close below harami low", "down"}:
            result["nison_harami_assessment"] = "BEARISH_HARAMI_CONTINUATION"
            return with_direction(result, state, "SELL", "a downtrend harami broke below its low")
        if first_color == "long white":
            result["nison_harami_assessment"] = "BULLISH_HARAMI_REVERSAL"
            return with_direction(result, state, "BUY", "a centered contained harami followed a decline and began with a long white body")
    if trend in {"up", "uptrend", "rally", "rising"}:
        if follow_through in {"above harami high", "close above harami high", "up"}:
            result["nison_harami_assessment"] = "BULLISH_HARAMI_CONTINUATION"
            return with_direction(result, state, "BUY", "an uptrend harami broke above its high")
        if first_color == "long black":
            result["nison_harami_assessment"] = "BEARISH_HARAMI_REVERSAL"
            return with_direction(result, state, "SELL", "a centered contained harami followed a rally and began with a long black body")
    result["view"] = "WAIT"
    result["reasons"] = ["harami trend, first-body color, and follow-through do not support a directional interpretation"]
    return result
