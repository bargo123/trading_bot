"""Anna Coulling's pin-bar and twin-bar price-rejection perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_price_rejection"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_pin_type",
    "ultimate_pin_location",
    "ultimate_pin_height",
    "ultimate_pin_count",
    "ultimate_trend",
    "ultimate_data_provenance",
)


def _missing(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    return list(dict.fromkeys(missing))


def evaluate(state):
    missing = _missing(state)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    pin_type = normalized_status(first(state, "ultimate_pin_type"))
    location = normalized_status(first(state, "ultimate_pin_location"))
    trend = normalized_status(first(state, "ultimate_trend"))
    height = number(first(state, "ultimate_pin_height"))
    count = number(first(state, "ultimate_pin_count"))
    if pin_type not in {"head", "tail", "twin", "twin bars", "twin bar"}:
        result["view"] = "WAIT"
        result["reasons"] = ["pin type is not an observed head, tail, or twin-bar rejection"]
        return result
    if location not in {"support", "resistance"} or height is None or height <= 0 or count is None or count < 1:
        result["view"] = "WAIT"
        result["reasons"] = ["pin location, positive height, and count are required"]
        return result
    if pin_type in {"twin", "twin bars", "twin bar"}:
        twin = normalized_status(first(state, "ultimate_twin_bar"))
        if twin in {"bear bull", "bear bullish"}:
            return with_direction(result, state, "SELL", "the observed twin bars show rejection by sellers")
        if twin in {"bull bear", "bullish bear"}:
            return with_direction(result, state, "BUY", "the observed twin bars show rejection by buyers")
        result["view"] = "WAIT"
        result["reasons"] = ["twin-bar direction is not explicitly observed"]
        return result
    signal = None
    if pin_type == "head" and (location == "resistance" or trend in {"down", "downtrend", "bear", "bearish"}):
        signal = "SELL"
    elif pin_type == "tail" and (location == "support" or trend in {"up", "uptrend", "bull", "bullish"}):
        signal = "BUY"
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["the source warns against this pin/location/trend combination"]
        return result
    result["ultimate_pin_strength"] = {"height": height, "count": count}
    return with_direction(result, state, signal, "the observed pin rejects an extreme in the source direction")
