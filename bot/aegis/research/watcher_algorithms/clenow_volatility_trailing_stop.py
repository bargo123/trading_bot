"""Clenow's optional ATR-scaled trailing-stop perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values

ALGORITHM_ID = "clenow_volatility_trailing_stop"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "side",
    "clenow_trailing_extreme_price",
    "clenow_trailing_current_price",
    "clenow_trailing_atr",
    "clenow_trailing_atr_multiple",
    "clenow_previous_stop_price",
    "clenow_trailing_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    candidate_side = side(state)
    missing = [key for key in KEYS if first(state, key) is None]
    if candidate_side not in {"BUY", "SELL"}:
        missing.append("side")
    if not explicitly_observed(first(state, "clenow_trailing_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("clenow_trailing_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    extreme = number(first(state, "clenow_trailing_extreme_price"))
    current = number(first(state, "clenow_trailing_current_price"))
    atr = number(first(state, "clenow_trailing_atr"))
    multiple = number(first(state, "clenow_trailing_atr_multiple"))
    previous = number(first(state, "clenow_previous_stop_price"))
    if any(value is None or value <= 0 for value in (extreme, current, atr, multiple, previous)):
        result["clenow_trailing_action"] = "WAIT_INVALID_STOP_INPUT"
        result["reasons"] = ["extreme, current price, ATR, multiple, and previous stop must be positive finite observations"]
        return result
    proposed = extreme - atr * multiple if candidate_side == "BUY" else extreme + atr * multiple
    result["clenow_proposed_stop_price"] = proposed
    if candidate_side == "BUY" and proposed > previous:
        result["clenow_trailing_action"] = "MOVE_STOP_UP"
        result["reasons"] = ["the volatility-adjusted long stop tightens upward after a new high"]
        return result
    if candidate_side == "SELL" and proposed < previous:
        result["clenow_trailing_action"] = "MOVE_STOP_DOWN"
        result["reasons"] = ["the volatility-adjusted short stop tightens downward after a new low"]
        return result
    result["clenow_trailing_action"] = "HOLD_STOP"
    result["reasons"] = ["the proposed volatility stop would loosen or leave the existing stop unchanged"]
    return result
