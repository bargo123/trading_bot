"""Bulkowski flag continuation and half-staff measured-move perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "bulkowski_flag_breakout"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = (
    "bulkowski_flag_trend_direction",
    "bulkowski_flag_duration_days",
    "bulkowski_flag_upper_slope",
    "bulkowski_flag_lower_slope",
    "bulkowski_flag_parallel_confirmed",
    "bulkowski_pre_flag_run_points",
    "bulkowski_preceding_trend_strong",
    "bulkowski_flag_volume_trend",
    "bulkowski_flag_breakout_direction",
    "bulkowski_flag_breakout_close_confirmed",
    "bulkowski_flag_breakout_price",
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
    trend = normalized_status(first(state, "bulkowski_flag_trend_direction")).upper()
    breakout_direction = normalized_status(first(state, "bulkowski_flag_breakout_direction")).upper()
    duration = number(first(state, "bulkowski_flag_duration_days"))
    upper = number(first(state, "bulkowski_flag_upper_slope"))
    lower = number(first(state, "bulkowski_flag_lower_slope"))
    run = number(first(state, "bulkowski_pre_flag_run_points"))
    breakout = number(first(state, "bulkowski_flag_breakout_price"))
    if trend not in {"UP", "DOWN"} or breakout_direction not in {"UP", "DOWN"} or any(value is None for value in (duration, upper, lower, run, breakout)):
        result["reasons"] = ["flag direction, slopes, duration, preceding run, and breakout must be observed"]
        return result
    if duration <= 0 or duration > 21 or run <= 0:
        result["reasons"] = ["the flag must be short and follow a steep, measured price run"]
        return result
    if first(state, "bulkowski_flag_parallel_confirmed") is not True or first(state, "bulkowski_preceding_trend_strong") is not True:
        result["reasons"] = ["flags require two parallel boundaries and a strong preceding trend"]
        return result
    if breakout_direction != trend or first(state, "bulkowski_flag_breakout_close_confirmed") is not True:
        result["reasons"] = ["the continuation breakout is not confirmed in the preceding-trend direction"]
        return result
    signal = "BUY" if breakout_direction == "UP" else "SELL"
    target = breakout + run if signal == "BUY" else breakout - run
    result.update({
        "bulkowski_measure_target": target,
        "bulkowski_flag_breakout_price": breakout,
        "bulkowski_flag_volume_preference": "downward",
    })
    if normalized_status(first(state, "bulkowski_flag_volume_trend")) != "down":
        result["warnings"] = ["the source prefers receding volume through the flag, but treats it as a guideline"]
    return with_direction(result, state, signal, "a short parallel flag after a strong run confirmed continuation in the prior trend direction")
