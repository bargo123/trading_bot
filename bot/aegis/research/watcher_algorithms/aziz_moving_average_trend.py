"""Andrew Aziz's moving-average support/resistance trend perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "aziz_moving_average_trend"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "aziz_ma_period",
    "aziz_price_relation_to_ma",
    "aziz_ma_role",
    "aziz_ma_confirmation",
    "aziz_ma_entry_near",
    "aziz_ma_break_invalidated",
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
    period = number(first(state, "aziz_ma_period"))
    relation = normalized_status(first(state, "aziz_price_relation_to_ma"))
    role = normalized_status(first(state, "aziz_ma_role"))
    if period is None or period <= 0 or relation not in {"above", "below"} or role not in {"support", "resistance"}:
        result["view"] = "WAIT"
        result["aziz_ma_assessment"] = "MA_INPUT_INVALID"
        result["reasons"] = ["moving-average period, price relation, and role must be explicit observed values"]
        return result
    if not _truthy(first(state, "aziz_ma_confirmation")):
        result["view"] = "WAIT"
        result["aziz_ma_assessment"] = "MA_CONFIRMATION_MISSING"
        result["reasons"] = ["the moving average has not been confirmed as support or resistance"]
        return result
    if not _truthy(first(state, "aziz_ma_entry_near")):
        result["view"] = "WAIT"
        result["aziz_ma_assessment"] = "ENTRY_NOT_NEAR_MA"
        result["reasons"] = ["the source prefers entry close to the confirmed moving-average level"]
        return result
    if _truthy(first(state, "aziz_ma_break_invalidated")):
        result["view"] = "WAIT"
        result["aziz_ma_assessment"] = "MA_TREND_INVALIDATED"
        result["reasons"] = ["price has broken the moving-average trend reference"]
        return result
    if relation == "above" and role == "support":
        signal = "BUY"
    elif relation == "below" and role == "resistance":
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["aziz_ma_assessment"] = "MA_ROLE_MISMATCH"
        result["reasons"] = ["above/support and below/resistance are the source-aligned trend combinations"]
        return result
    result["aziz_ma_assessment"] = "CONFIRMED_MA_TREND"
    result["aziz_ma_period"] = period
    return with_direction(result, state, signal, "price is near a confirmed moving-average support/resistance trend")
