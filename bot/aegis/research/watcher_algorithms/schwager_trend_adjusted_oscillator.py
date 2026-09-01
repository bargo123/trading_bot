"""Schwager's trend-aware oscillator-extreme filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "schwager_trend_adjusted_oscillator"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_oscillator_trend",
    "schwager_oscillator_extreme",
    "schwager_trend_adjustment_observed",
    "schwager_trend_adjusted_oscillator_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and "observed" in label and "trend" in label and "oscillator" in label and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "schwager_trend_adjusted_oscillator_data_provenance")):
        missing.append("schwager_trend_adjusted_oscillator_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = normalized_status(first(state, "schwager_oscillator_trend"))
    extreme = normalized_status(first(state, "schwager_oscillator_extreme"))
    if trend not in {"up", "uptrend", "down", "downtrend", "range", "sideways"} or extreme not in {"overbought", "oversold"}:
        result["schwager_trend_adjustment"] = "INPUT_INVALID"
        result["reasons"] = ["trend and oscillator extreme must be observed as explicit states"]
        return result
    if not _truth(first(state, "schwager_trend_adjustment_observed")):
        result["schwager_trend_adjustment"] = "LEVEL_ADJUSTMENT_UNRESOLVED"
        result["reasons"] = ["oscillator thresholds have not been adjusted or interpreted for the observed regime"]
        return result
    if trend in {"up", "uptrend"} and extreme == "oversold":
        result["schwager_trend_adjustment"] = "UPTREND_OVERSOLD_ENTRY"
        return with_direction(result, state, "BUY", "the oversold reading is the trend-compatible oscillator opportunity in an uptrend")
    if trend in {"up", "uptrend"}:
        result["schwager_trend_adjustment"] = "UPTREND_OVERBOUGHT_COUNTERTREND_WARNING"
        result["warnings"] = ["sustained overbought readings in an uptrend can produce premature countertrend sells"]
        result["reasons"] = ["the source favors trend-compatible pullbacks over countertrend sells in an uptrend"]
        return result
    if trend in {"down", "downtrend"} and extreme == "overbought":
        result["schwager_trend_adjustment"] = "DOWNTREND_OVERBOUGHT_ENTRY"
        return with_direction(result, state, "SELL", "the overbought reading is the trend-compatible oscillator opportunity in a downtrend")
    if trend in {"down", "downtrend"}:
        result["schwager_trend_adjustment"] = "DOWNTREND_OVERSOLD_COUNTERTREND_WARNING"
        result["warnings"] = ["sustained oversold readings in a downtrend can produce premature countertrend buys"]
        result["reasons"] = ["the source favors trend-compatible rallies over countertrend buys in a downtrend"]
        return result
    result["schwager_trend_adjustment"] = "RANGE_EXTREME_CONTEXT"
    return with_direction(result, state, "SELL" if extreme == "overbought" else "BUY", "the oscillator extreme is interpreted as a range-context reversal alert")
