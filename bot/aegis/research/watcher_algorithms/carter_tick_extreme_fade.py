"""John Carter's observed breadth-$TICK extreme fade study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_tick_extreme_fade"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_tick_market",
    "carter_tick_value",
    "carter_tick_minutes_et",
    "carter_tick_zero_cross_seen",
    "carter_tick_hard_stopouts",
    "carter_tick_data_provenance",
)
MARKETS = {"es", "ym", "spy", "dia", "nq", "rty", "index mirror", "mirrors index"}


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_tick_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_tick_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    market = normalized_status(first(state, "carter_tick_market"))
    if market not in MARKETS:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the source tick breadth signal is for observed equity-index or mirrored markets"]
        return result
    tick = number(first(state, "carter_tick_value"))
    minutes = number(first(state, "carter_tick_minutes_et"))
    hard_stopouts = number(first(state, "carter_tick_hard_stopouts"))
    if tick is None or minutes is None or hard_stopouts is None or not 0 <= minutes < 1440:
        result["view"] = "WAIT"
        result["reasons"] = ["tick breadth, ET time, and hard-stop count must be finite observations"]
        return result
    if not 600 <= minutes <= 930:
        result["view"] = "WAIT"
        result["reasons"] = ["the source tick fade window is 10:00 through 15:30 ET"]
        return result
    if hard_stopouts >= 2:
        result["view"] = "WAIT"
        result["reasons"] = ["two consecutive hard-stop tick fades end the source setup for the day"]
        return result
    if not _truthy(first(state, "carter_tick_zero_cross_seen")):
        result["view"] = "WAIT"
        result["reasons"] = ["a one-sided tick session needs a causal move back through zero before another fade"]
        return result
    if number(first(state, "carter_tick_percent_above_zero_by_noon")) is not None and number(first(state, "carter_tick_percent_above_zero_by_noon")) > 0.85 and minutes >= 720:
        result["view"] = "WAIT"
        result["reasons"] = ["the source power-day filter disables later fades after an overwhelmingly one-sided morning"]
        return result
    if tick >= 1000:
        signal = "SELL"
    elif tick <= -1000:
        signal = "BUY"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the breadth reading has not reached the explicit plus/minus 1000 extreme"]
        return result
    normalized_market = market.replace(" ", "")
    if normalized_market == "ym":
        stop_points, target_points = 30.0, 20.0
    elif normalized_market == "es":
        stop_points, target_points = 3.0, 2.0
    else:
        stop_points = target_points = None
    result["carter_tick_stop_points"] = stop_points
    result["carter_tick_target_points"] = target_points
    result["carter_tick_time_limit_minutes"] = 35.0
    return with_direction(result, state, signal, "the observed breadth extreme is faded in the source direction")
