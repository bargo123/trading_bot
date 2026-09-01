"""Schwager's oscillator-alert-then-price-confirmation perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "schwager_oscillator_price_confirmation"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_oscillator_extreme",
    "schwager_price_reversal_direction",
    "schwager_price_reversal_confirmed",
    "schwager_oscillator_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "oscillator" in label and any(token in label for token in ("price", "bar", "quote")) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_oscillator_data_provenance")):
        missing.append("schwager_oscillator_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    extreme = normalized_status(first(state, "schwager_oscillator_extreme"))
    reversal = normalized_status(first(state, "schwager_price_reversal_direction"))
    if extreme not in {"overbought", "oversold"} or reversal not in {"up", "down"}:
        result["schwager_oscillator_assessment"] = "INPUT_INVALID"
        result["reasons"] = ["overbought/oversold and a confirmed price-reversal direction must be explicit"]
        return result
    if not _truth(first(state, "schwager_price_reversal_confirmed")):
        result["schwager_oscillator_assessment"] = "ALERT_ONLY"
        result["reasons"] = ["the oscillator extreme is an alert; a definitive price reversal is still required"]
        return result
    if extreme == "oversold" and reversal == "up":
        result["schwager_oscillator_assessment"] = "OVERSOLD_PRICE_CONFIRMED"
        return with_direction(result, state, "BUY", "an oversold alert was followed by a confirmed upside price reversal")
    if extreme == "overbought" and reversal == "down":
        result["schwager_oscillator_assessment"] = "OVERBOUGHT_PRICE_CONFIRMED"
        return with_direction(result, state, "SELL", "an overbought alert was followed by a confirmed downside price reversal")
    result["schwager_oscillator_assessment"] = "EXTREME_REVERSAL_MISMATCH"
    result["reasons"] = ["the confirmed price move does not reverse the observed oscillator extreme"]
    return result
