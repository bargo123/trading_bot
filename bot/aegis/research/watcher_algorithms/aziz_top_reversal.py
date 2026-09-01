"""Andrew Aziz's scanner-plus-confirmation top-reversal study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "aziz_top_reversal"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_consecutive_up_candles",
    "aziz_rsi",
    "aziz_level_role",
    "aziz_confirmation_candle",
    "aziz_new_low_triggered",
    "aziz_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "aziz_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("aziz_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candles = number(first(state, "aziz_consecutive_up_candles"))
    rsi = number(first(state, "aziz_rsi"))
    if candles is None or candles < 4:
        result["view"] = "WAIT"
        result["aziz_top_assessment"] = "BUYING_RUN_NOT_EXTREME"
        result["reasons"] = ["the scanner requires at least four consecutive up candles"]
        return result
    if rsi is None or not 0 <= rsi <= 100 or rsi <= 90:
        result["view"] = "WAIT"
        result["aziz_top_assessment"] = "RSI_NOT_EXTREME"
        result["reasons"] = ["the source top setup requires RSI above ninety"]
        return result
    if normalized_status(first(state, "aziz_level_role")) != "resistance":
        result["view"] = "WAIT"
        result["aziz_top_assessment"] = "RESISTANCE_NOT_CONFIRMED"
        result["reasons"] = ["the reversal must be at an observed significant resistance level"]
        return result
    candle = normalized_status(first(state, "aziz_confirmation_candle"))
    if not any(token in candle for token in ("doji", "indecision", "bearish")):
        result["view"] = "WAIT"
        result["aziz_top_assessment"] = "REVERSAL_CANDLE_NOT_CONFIRMED"
        result["reasons"] = ["a bearish or indecision confirmation candle is required"]
        return result
    if not _truthy(first(state, "aziz_new_low_triggered")):
        result["view"] = "WAIT"
        result["aziz_top_assessment"] = "TRIGGER_NOT_CONFIRMED"
        result["reasons"] = ["the source enters after a new five-minute low"]
        return result
    result["aziz_top_assessment"] = "CONFIRMED_TOP_REVERSAL"
    result["aziz_rsi"] = rsi
    return with_direction(result, state, "SELL", "the extreme buying run, resistance, reversal candle, and new-low trigger agree")
