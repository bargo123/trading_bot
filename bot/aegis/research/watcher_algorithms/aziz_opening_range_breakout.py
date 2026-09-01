"""Andrew Aziz's opening-range breakout entry perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "aziz_opening_range_breakout"
SOURCES = ("Andrew Aziz — How to Day Trade for a Living",)
KEYS = (
    "side",
    "aziz_orb_range_minutes",
    "aziz_orb_high",
    "aziz_orb_low",
    "aziz_orb_atr",
    "aziz_orb_price",
    "aziz_orb_break_direction",
    "aziz_orb_break_confirmed",
    "aziz_orb_vwap",
    "aziz_orb_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "aziz_orb_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("aziz_orb_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["aziz_orb_signal_role"] = "ENTRY_ONLY_NO_TARGET"
    result["aziz_orb_thresholds"] = {
        "supported_range_minutes": [5, 15, 30, 60],
        "opening_range_must_be_smaller_than_atr": True,
        "target_defined_by_this_perspective": False,
    }
    side = normalized_status(first(state, "side")).upper()
    minutes = number(first(state, "aziz_orb_range_minutes"))
    high = number(first(state, "aziz_orb_high"))
    low = number(first(state, "aziz_orb_low"))
    atr = number(first(state, "aziz_orb_atr"))
    price = number(first(state, "aziz_orb_price"))
    vwap = number(first(state, "aziz_orb_vwap"))
    direction = normalized_status(first(state, "aziz_orb_break_direction"))
    if side not in {"BUY", "SELL"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the ORB entry must have an explicit BUY or SELL candidate side"]
        return result
    if minutes not in {5.0, 15.0, 30.0, 60.0}:
        result["view"] = "WAIT"
        result["reasons"] = ["the source ORB uses a 5-, 15-, 30-, or 60-minute opening range"]
        return result
    if any(value is None for value in (high, low, atr, price, vwap)) or high <= low or atr <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["opening-range high/low, ATR, price, and VWAP must be finite with valid geometry"]
        return result
    if high - low >= atr:
        result["view"] = "WAIT"
        result["reasons"] = ["the source requires the opening range to be smaller than the stock ATR"]
        return result
    if not volman_truth(first(state, "aziz_orb_break_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the opening-range break is not confirmed"]
        return result
    if direction == "up" and side == "BUY" and price > high and price > vwap:
        result["aziz_orb_invalidation"] = "CLOSE_BELOW_VWAP"
        return with_direction(result, state, "BUY", "confirmed upside opening-range break is above the range and VWAP")
    if direction == "down" and side == "SELL" and price < low and price < vwap:
        result["aziz_orb_invalidation"] = "CLOSE_ABOVE_VWAP"
        return with_direction(result, state, "SELL", "confirmed downside opening-range break is below the range and VWAP")
    result["view"] = "WAIT"
    result["reasons"] = ["break direction, candidate side, range boundary, and VWAP invalidation do not agree"]
    return result
