"""Retail-positioning contrarian perspective described by Silvani."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "silvani_retail_contrarian"
SOURCES = ("Beat the Forex Dealer",)
KEYS = (
    "silvani_crowded_side",
    "silvani_positioning_extreme",
    "silvani_market_trend",
    "silvani_data_provenance",
)


def _missing(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "silvani_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("silvani_data_provenance")
    return list(dict.fromkeys(missing))


def evaluate(state):
    missing = _missing(state)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "silvani_positioning_extreme")):
        result["view"] = "WAIT"
        result["reasons"] = ["retail positioning is not observed as an extreme crowding condition"]
        return result
    crowded = normalized_status(first(state, "silvani_crowded_side"))
    trend = normalized_status(first(state, "silvani_market_trend"))
    if crowded == "sell" and trend == "up":
        return with_direction(result, state, "BUY", "extreme retail short crowding is a contrarian confirmation of the observed uptrend")
    if crowded == "buy" and trend == "down":
        return with_direction(result, state, "SELL", "extreme retail long crowding is a contrarian confirmation of the observed downtrend")
    result["view"] = "WAIT"
    result["reasons"] = ["retail crowding and market trend do not form the source contrarian alignment"]
    return result
