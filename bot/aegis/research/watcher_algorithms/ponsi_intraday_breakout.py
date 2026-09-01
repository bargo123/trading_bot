"""Ponsi triangle breakout with prior-trend and liquidity-session filters."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, ponsi_missing, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_intraday_breakout"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_triangle_type",
    "ponsi_prior_trend",
    "ponsi_session_quality",
    "ponsi_breakout_direction",
    "ponsi_breakout_confirmation",
    "ponsi_data_provenance",
)


def evaluate(state):
    missing = ponsi_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    triangle = normalized_status(first(state, "ponsi_triangle_type"))
    trend = normalized_status(first(state, "ponsi_prior_trend"))
    session = normalized_status(first(state, "ponsi_session_quality"))
    breakout = normalized_status(first(state, "ponsi_breakout_direction"))
    if "low liquidity" in session or not any(token in session for token in ("london", "new york", "high liquidity", "high volume")):
        result["view"] = "WAIT"
        result["reasons"] = ["intraday breakout is not in a source-supported high-liquidity session"]
        return result
    if not volman_truth(first(state, "ponsi_breakout_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["triangle has no confirmed breakout"]
        return result
    if triangle == "ascending triangle" and trend == "up" and breakout == "up":
        return with_direction(result, state, "BUY", "ascending triangle breakout agrees with the prior uptrend in a liquid session")
    if triangle == "descending triangle" and trend == "down" and breakout == "down":
        return with_direction(result, state, "SELL", "descending triangle breakout agrees with the prior downtrend in a liquid session")
    result["view"] = "WAIT"
    result["reasons"] = ["triangle, prior trend, and breakout direction are not aligned"]
    return result
