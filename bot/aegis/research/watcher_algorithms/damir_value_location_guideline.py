"""Laurentiu Damir's trend-aware advantageous value/excess entry zones."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "damir_value_location_guideline"
SOURCES = ("Laurentiu Damir — Price Action Breakdown",)
KEYS = (
    "damir_value_trend",
    "damir_current_price",
    "damir_value_high",
    "damir_value_low",
    "damir_control_price",
    "damir_excess_high",
    "damir_excess_low",
    "damir_location_data_provenance",
    "damir_location_stop_pips",
    "damir_location_target_pips",
)


def _trend(value: object) -> str | None:
    normalized = normalized_status(value)
    if normalized in {"up", "uptrend", "bull", "bullish"}:
        return "uptrend"
    if normalized in {"down", "downtrend", "bear", "bearish"}:
        return "downtrend"
    if normalized in {"sideways", "horizontal", "balance", "balanced"}:
        return "sideways"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "damir_location_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("damir_location_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = _trend(first(state, "damir_value_trend"))
    candidate_side = side(state)
    price = number(first(state, "damir_current_price"))
    high = number(first(state, "damir_value_high"))
    low = number(first(state, "damir_value_low"))
    control = number(first(state, "damir_control_price"))
    excess_high = number(first(state, "damir_excess_high"))
    excess_low = number(first(state, "damir_excess_low"))
    stop = number(first(state, "damir_location_stop_pips"))
    target = number(first(state, "damir_location_target_pips"))

    if trend is None:
        result["reasons"] = ["value location requires an observed uptrend, downtrend, or sideways market"]
        return result
    if any(value is None for value in (price, high, low, control, excess_high, excess_low)) or not excess_low <= low < control < high <= excess_high:
        result["reasons"] = ["value, control, and excess boundaries must be finite and ordered"]
        return result
    if price < excess_low or price > excess_high:
        result["reasons"] = ["current price is outside the observed value and excess boundaries"]
        return result
    if stop is None or target is None or stop <= 0 or target <= stop:
        result["reasons"] = ["the source location study requires positive reward greater than risk"]
        return result
    if candidate_side not in {"BUY", "SELL"}:
        result["reasons"] = ["a BUY or SELL candidate side is required to apply the location guideline"]
        return result

    zone = None
    if candidate_side == "BUY":
        if trend == "uptrend" and excess_low <= price <= control:
            zone = "uptrend_buy_excess_to_control"
        elif trend == "downtrend" and excess_low <= price <= low:
            zone = "downtrend_buy_below_value_excess"
        elif trend == "sideways" and excess_low <= price <= control:
            zone = "sideways_buy_excess_to_control"
    else:
        if trend == "uptrend" and high <= price <= excess_high:
            zone = "uptrend_sell_above_value_excess"
        elif trend == "downtrend" and control <= price <= excess_high:
            zone = "downtrend_sell_excess_to_control"
        elif trend == "sideways" and control <= price <= excess_high:
            zone = "sideways_sell_control_to_excess"

    if zone is None:
        result["reasons"] = ["current price is not in the source's advantageous zone for this trend and side"]
        return result
    result["damir_advantageous_zone"] = zone
    result["damir_value_location"] = {"price": price, "low": low, "control": control, "high": high}
    return with_direction(result, state, candidate_side, "current price is in the trend-aware value/excess zone")
