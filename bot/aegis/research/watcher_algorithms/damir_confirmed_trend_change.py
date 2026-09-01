"""Laurentiu Damir's confirmed swing-based trend-change perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, with_direction

ALGORITHM_ID = "damir_confirmed_trend_change"
SOURCES = ("Laurentiu Damir — Trade the Price Action",)
KEYS = (
    "damir_prior_trend",
    "damir_last_swing_breached",
    "damir_correction_after_breach",
    "damir_new_swing_direction",
    "damir_new_swing_confirmed",
    "damir_trend_change_data_provenance",
)


def _truth(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "uptrend", "bull", "bullish", "buy", "long"}:
        return "up"
    if normalized in {"down", "downtrend", "bear", "bearish", "sell", "short"}:
        return "down"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    prior = _direction(first(state, "damir_prior_trend"))
    new_direction = _direction(first(state, "damir_new_swing_direction"))
    provenance = first(state, "damir_trend_change_data_provenance")
    missing = [
        key
        for key, value in (
            ("damir_prior_trend", prior),
            ("damir_last_swing_breached", first(state, "damir_last_swing_breached")),
            ("damir_correction_after_breach", first(state, "damir_correction_after_breach")),
            ("damir_new_swing_direction", new_direction),
            ("damir_new_swing_confirmed", first(state, "damir_new_swing_confirmed")),
        )
        if value is None or value == ""
    ]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped")):
        missing.append("damir_trend_change_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if prior not in {"up", "down"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the prior swing trend is not a recognized direction"]
        return result
    if not _truth(first(state, "damir_last_swing_breached")):
        result["view"] = "WAIT"
        result["reasons"] = ["the last lower-high or higher-low has not been breached"]
        return result
    if not _truth(first(state, "damir_correction_after_breach")):
        result["view"] = "WAIT"
        result["reasons"] = ["the breach has not been followed by the required correction"]
        return result
    if not _truth(first(state, "damir_new_swing_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the new higher-high or lower-low is not confirmed"]
        return result
    expected = "down" if prior == "up" else "up"
    if new_direction != expected:
        result["view"] = "WAIT"
        result["reasons"] = ["the confirmed new swing does not reverse the prior trend"]
        return result
    signal = "BUY" if expected == "up" else "SELL"
    result["damir_trend_change_confirmed"] = True
    return with_direction(
        result,
        state,
        signal,
        "the prior swing was breached, corrected, and followed by a confirmed opposite swing",
    )
