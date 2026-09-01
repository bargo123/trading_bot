"""Price-in-Time NTZ range-projection and target-level perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "price_in_time_ntz_projection"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "side",
    "pit_projection_direction",
    "pit_projection_width_pips",
    "pit_projection_breakout_price",
    "pit_projection_pip_size",
    "pit_projection_level",
    "pit_projection_target_price",
    "pit_projection_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("measured_ntz_width_and_projection",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    direction = normalized_status(first(state, "pit_projection_direction"))
    width = number(first(state, "pit_projection_width_pips"))
    breakout = number(first(state, "pit_projection_breakout_price"))
    pip_size = number(first(state, "pit_projection_pip_size"))
    level = number(first(state, "pit_projection_level"))
    target = number(first(state, "pit_projection_target_price"))
    missing = [
        key for key, value in (
            ("side", candidate_side),
            ("pit_projection_direction", direction),
            ("pit_projection_width_pips", width),
            ("pit_projection_breakout_price", breakout),
            ("pit_projection_pip_size", pip_size),
            ("pit_projection_level", level),
            ("pit_projection_target_price", target),
        ) if value is None
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if direction not in {"up", "down"} or width <= 0 or breakout <= 0 or pip_size <= 0 or level <= 0 or level != int(level) or target <= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["NTZ projection requires positive range, price, pip size, and integer target level"]
        return result
    if not explicitly_observed(first(state, "pit_projection_data_provenance"), accepted=("observed", "measured")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["pit_projection_data_provenance"]
        return result
    sign = 1 if direction == "up" else -1
    projected = breakout + sign * width * pip_size * level
    result["pit_projected_target_price"] = projected
    result["pit_projection_error_pips"] = abs(target - projected) / pip_size
    if abs(target - projected) > pip_size * 0.5:
        result["view"] = "WAIT"
        result["reasons"] = ["observed target does not match the measured NTZ range projection"]
        return result
    result["pit_projection_assessment"] = f"TARGET_{int(level)}_CONFIRMED"
    signal = "BUY" if direction == "up" else "SELL"
    return with_direction(result, state, signal, "target is projected by repeating the observed NTZ range from the breakout")
