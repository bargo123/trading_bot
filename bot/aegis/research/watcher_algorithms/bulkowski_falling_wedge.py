"""Bulkowski falling-wedge structure and breakout perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "bulkowski_falling_wedge"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = (
    "bulkowski_wedge_type",
    "bulkowski_wedge_upper_slope",
    "bulkowski_wedge_lower_slope",
    "bulkowski_wedge_touches",
    "bulkowski_wedge_duration_days",
    "bulkowski_wedge_volume_trend",
    "bulkowski_wedge_breakout_direction",
    "bulkowski_wedge_breakout_confirmed",
    "bulkowski_wedge_breakout_price",
    "bulkowski_wedge_high",
    "bulkowski_wedge_low",
    "bulkowski_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "bulkowski_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("bulkowski_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "bulkowski_wedge_type")) != "falling":
        result["reasons"] = ["this perspective requires a falling wedge"]
        return result
    upper = number(first(state, "bulkowski_wedge_upper_slope"))
    lower = number(first(state, "bulkowski_wedge_lower_slope"))
    touches = number(first(state, "bulkowski_wedge_touches"))
    duration = number(first(state, "bulkowski_wedge_duration_days"))
    breakout = number(first(state, "bulkowski_wedge_breakout_price"))
    high = number(first(state, "bulkowski_wedge_high"))
    low = number(first(state, "bulkowski_wedge_low"))
    direction = normalized_status(first(state, "bulkowski_wedge_breakout_direction")).upper()
    if any(value is None for value in (upper, lower, touches, duration, breakout, high, low)) or direction not in {"UP", "DOWN"}:
        result["reasons"] = ["wedge slopes, touches, duration, breakout, and range must be observed"]
        return result
    if not upper < lower < 0 or touches < 5 or duration < 21 or high <= low:
        result["reasons"] = ["the wedge must have two converging down-sloping lines, five touches, three weeks, and positive height"]
        return result
    if first(state, "bulkowski_wedge_breakout_confirmed") is not True:
        result["reasons"] = ["the wedge breakout is not confirmed"]
        return result
    signal = "BUY" if direction == "UP" else "SELL"
    height = high - low
    target = high if signal == "BUY" else breakout - height
    result.update({
        "bulkowski_measure_target": target,
        "bulkowski_wedge_height": height,
        "bulkowski_wedge_volume_preference": "downward_until_breakout",
    })
    if normalized_status(first(state, "bulkowski_wedge_volume_trend")) != "down":
        result["warnings"] = ["the source usually observes declining volume through the wedge, but treats it as a guideline"]
    return with_direction(result, state, signal, "a measured falling wedge has converging down-sloping boundaries and a confirmed breakout")
