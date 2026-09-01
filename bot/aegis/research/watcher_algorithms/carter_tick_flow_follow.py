"""John Carter's persistent breadth-$TICK flow-following perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_tick_flow_follow"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_flow_market",
    "carter_flow_minutes_et",
    "carter_flow_tick_value",
    "carter_flow_tick_ema8",
    "carter_flow_tick_ema21",
    "carter_flow_persistent_extreme",
    "carter_flow_zero_retest_rejected",
    "carter_flow_data_provenance",
)
MARKETS = {"es", "ym", "spy", "dia", "nq", "rty"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_flow_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_flow_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    market = normalized_status(first(state, "carter_flow_market")).replace(" ", "")
    if market not in MARKETS:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the source flow-following signal requires an observed equity-index breadth proxy"]
        return result
    minutes = number(first(state, "carter_flow_minutes_et"))
    tick = number(first(state, "carter_flow_tick_value"))
    ema8 = number(first(state, "carter_flow_tick_ema8"))
    ema21 = number(first(state, "carter_flow_tick_ema21"))
    if any(value is None for value in (minutes, tick, ema8, ema21)) or not 0 <= minutes < 1440:
        result["reasons"] = ["tick breadth, EMA context, and ET time must be finite observations"]
        return result
    if not 600 <= minutes <= 930:
        result["reasons"] = ["the source tick-flow window is 10:00 through 15:30 ET"]
        return result
    if first(state, "carter_flow_persistent_extreme") is not True:
        result["reasons"] = ["a single extreme probe is not enough to classify persistent institutional flow"]
        return result
    if first(state, "carter_flow_zero_retest_rejected") is not True:
        result["reasons"] = ["the flow-following entry requires a causal rejection of the zero-line retest"]
        return result
    if ema8 < ema21 < 0 and tick < 0:
        signal = "SELL"
        regime = "persistent_selling"
    elif ema8 > ema21 > 0 and tick > 0:
        signal = "BUY"
        regime = "persistent_buying"
    else:
        result["reasons"] = ["the 8/21 breadth EMAs do not show aligned persistent flow"]
        return result
    result["carter_flow_regime"] = regime
    result["carter_flow_emergency_tick_reversal"] = 600.0
    result["carter_flow_emergency_price_stop_points"] = 4.0 if market == "es" else None
    return with_direction(result, state, signal, "persistent breadth flow and a rejected zero-line retest support following the institutional move")
