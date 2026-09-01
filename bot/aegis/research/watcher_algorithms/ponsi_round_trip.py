"""Ponsi's short-term round-number reaction with explicit cost geometry."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, ponsi_missing, values, with_direction

ALGORITHM_ID = "ponsi_round_trip"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "side",
    "ponsi_round_trip_level",
    "ponsi_round_trip_extension_pips",
    "ponsi_round_trip_bounce_count",
    "ponsi_round_trip_reversal_direction",
    "ponsi_round_trip_spread_pips",
    "ponsi_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = ponsi_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    extension = number(first(state, "ponsi_round_trip_extension_pips"))
    bounce_count = number(first(state, "ponsi_round_trip_bounce_count"))
    spread = number(first(state, "ponsi_round_trip_spread_pips"))
    level = normalized_status(first(state, "ponsi_round_trip_level"))
    reversal = normalized_status(first(state, "ponsi_round_trip_reversal_direction"))
    if any(value is None or value < 0 for value in (extension, bounce_count, spread)):
        result["ponsi_round_trip_assessment"] = "INVALID_INPUTS"
        result["reasons"] = ["extension, bounce count, and spread must be finite non-negative observations"]
        return result
    if spread > 5.0:
        result["ponsi_round_trip_assessment"] = "SPREAD_TOO_WIDE"
        result["reasons"] = ["the source excludes pairs with more than five pips of spread for this short-term setup"]
        return result
    if extension < 20.0:
        result["ponsi_round_trip_assessment"] = "EXTENSION_TOO_SMALL"
        result["reasons"] = ["the source requires at least a 20-pip extension from the 20-period moving average"]
        return result
    if bounce_count < 1 or bounce_count != int(bounce_count):
        result["ponsi_round_trip_assessment"] = "ROUND_NUMBER_TEST_MISSING"
        result["reasons"] = ["the round number has not been observed as a tested level"]
        return result
    signal = "BUY" if level == "support" and reversal in {"up", "buy", "bullish"} else (
        "SELL" if level == "resistance" and reversal in {"down", "sell", "bearish"} else None
    )
    if signal is None:
        result["ponsi_round_trip_assessment"] = "REACTION_DIRECTION_MISMATCH"
        result["reasons"] = ["the round-number level and observed reversal direction do not agree"]
        return result
    stop = 15.0 + spread
    result["ponsi_round_trip_assessment"] = "CONFIRMED_ROUND_TRIP"
    result["ponsi_round_trip_stop_pips"] = stop
    result["ponsi_round_trip_first_target_pips"] = stop
    result["ponsi_round_trip_preferred_bounce"] = bounce_count == 1
    return with_direction(result, state, signal, "a measured round-number extension and reaction pass the short-term spread limit")
