"""Bulkowski ascending-triangle structure and breakout perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "bulkowski_ascending_triangle"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
KEYS = (
    "bulkowski_triangle_type",
    "bulkowski_triangle_top_slope",
    "bulkowski_triangle_bottom_slope",
    "bulkowski_triangle_top_touches",
    "bulkowski_triangle_bottom_touches",
    "bulkowski_triangle_crossings",
    "bulkowski_triangle_volume_trend",
    "bulkowski_triangle_breakout_direction",
    "bulkowski_triangle_breakout_close_confirmed",
    "bulkowski_triangle_breakout_price",
    "bulkowski_triangle_height",
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
    if normalized_status(first(state, "bulkowski_triangle_type")) != "ascending":
        result["reasons"] = ["this perspective requires an ascending triangle"]
        return result
    top_slope = number(first(state, "bulkowski_triangle_top_slope"))
    bottom_slope = number(first(state, "bulkowski_triangle_bottom_slope"))
    top_touches = number(first(state, "bulkowski_triangle_top_touches"))
    bottom_touches = number(first(state, "bulkowski_triangle_bottom_touches"))
    crossings = number(first(state, "bulkowski_triangle_crossings"))
    breakout = number(first(state, "bulkowski_triangle_breakout_price"))
    height = number(first(state, "bulkowski_triangle_height"))
    direction = normalized_status(first(state, "bulkowski_triangle_breakout_direction")).upper()
    if any(value is None for value in (top_slope, bottom_slope, top_touches, bottom_touches, crossings, breakout, height)) or direction not in {"UP", "DOWN"}:
        result["reasons"] = ["triangle slopes, touches, crossings, breakout, and height must be observed"]
        return result
    if abs(top_slope) > 0.02 or bottom_slope <= 0 or top_touches < 2 or bottom_touches < 2 or crossings < 3 or height <= 0:
        result["reasons"] = ["the structure lacks a horizontal top, rising bottom, repeated touches, or filled crossings"]
        return result
    if first(state, "bulkowski_triangle_breakout_close_confirmed") is not True:
        result["reasons"] = ["the triangle breakout close is not confirmed"]
        return result
    signal = "BUY" if direction == "UP" else "SELL"
    result.update({
        "bulkowski_measure_target": breakout + height if signal == "BUY" else breakout - height,
        "bulkowski_triangle_breakout_price": breakout,
        "bulkowski_triangle_volume_preference": "downward_until_breakout",
    })
    if normalized_status(first(state, "bulkowski_triangle_volume_trend")) != "down":
        result["warnings"] = ["the source prefers volume to taper through the triangle, but treats it as a guideline"]
    return with_direction(result, state, signal, "an observed ascending triangle has the required repeated boundaries and confirmed breakout")
