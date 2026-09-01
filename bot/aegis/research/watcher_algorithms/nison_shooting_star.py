"""Nison shooting-star rejection after an uptrend."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_shooting_star"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_shooting_star_present",
    "nison_shooting_star_trend",
    "nison_shooting_star_shape",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_shooting_star_present")):
        result["view"] = "WAIT"
        result["reasons"] = ["shooting-star observation is not confirmed"]
        return result
    if normalized_status(first(state, "nison_shooting_star_shape")) != "long upper shadow small body near low":
        result["view"] = "WAIT"
        result["reasons"] = ["shooting-star upper-shadow rejection shape is not confirmed"]
        return result
    if normalized_status(first(state, "nison_shooting_star_trend")) not in {"up", "uptrend", "rally", "rising"}:
        result["view"] = "WAIT"
        result["reasons"] = ["a shooting star requires a preceding uptrend"]
        return result
    result["nison_shooting_star_assessment"] = "CONFIRMED_AFTER_UPTREND"
    return with_direction(result, state, "SELL", "long upper-shadow rejection followed an uptrend")
