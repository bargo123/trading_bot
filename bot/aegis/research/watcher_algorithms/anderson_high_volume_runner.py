"""Brian Anderson's high-volume-runner review for the read-only Watcher."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "anderson_high_volume_runner"
SOURCES = ("Brian Anderson — The 1 Hour Trade",)
KEYS = (
    "anderson_volume_ratio",
    "anderson_volume_provenance",
    "anderson_time_from_open_min",
    "anderson_opening_range_breakout",
    "anderson_long_term_support",
    "anderson_tight_low_volume_base",
    "anderson_new_long_term_high",
    "anderson_moving_average_breakout",
    "anderson_resistance_overhead",
    "anderson_recent_selloff",
    "anderson_large_gap_up",
    "anderson_ma_resistance",
    "anderson_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "anderson_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("anderson_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if str(first(state, "side") or "").upper() != "BUY":
        result["view"] = "WAIT"
        result["reasons"] = ["the source high-volume-runner setup is a long breakout perspective"]
        return result
    volume_provenance = normalized_status(first(state, "anderson_volume_provenance"))
    if any(token in volume_provenance for token in ("tick", "proxy", "synthetic", "unknown", "unavailable")):
        result["view"] = "WAIT"
        result["warnings"] = ["tick activity or synthetic volume cannot validate the source volume condition"]
        result["reasons"] = ["high-volume-runner requires observed traded volume"]
        return result
    volume_ratio = number(first(state, "anderson_volume_ratio"))
    if volume_ratio is None or volume_ratio < 30.0:
        result["view"] = "WAIT"
        result["reasons"] = ["relative volume is below the source 30x scanner condition"]
        return result
    minutes = number(first(state, "anderson_time_from_open_min"))
    if minutes is None or minutes < 0 or minutes > 20.0:
        result["view"] = "WAIT"
        result["reasons"] = ["the source opening review window ends 20 minutes after the open"]
        return result
    if not volman_truth(first(state, "anderson_opening_range_breakout")):
        result["view"] = "WAIT"
        result["reasons"] = ["price has not confirmed a break above the opening-range high"]
        return result
    red_flags = [
        key for key in ("anderson_resistance_overhead", "anderson_recent_selloff", "anderson_large_gap_up", "anderson_ma_resistance")
        if volman_truth(first(state, key))
    ]
    if red_flags:
        result["view"] = "WAIT"
        result["reasons"] = ["red flag review blocks the runner: " + ", ".join(red_flags)]
        return result
    green_flags = [
        key for key in ("anderson_long_term_support", "anderson_tight_low_volume_base", "anderson_new_long_term_high", "anderson_moving_average_breakout")
        if volman_truth(first(state, key))
    ]
    if len(green_flags) < 3:
        result["view"] = "WAIT"
        result["reasons"] = ["fewer than three independent green flags are confirmed"]
        return result
    return with_direction(result, state, "BUY", "opening-range breakout has real relative volume and aligned green flags")
