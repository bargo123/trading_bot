"""Van Tharp narrow-range setup plus directional timing perspective.

The source describes compression as a setup, not a complete entry system: a
trend must be present, the range must contract, and a separate entry trigger
must start the expected move.  This module records that sequence for the
read-only Watcher; it never submits or sizes an order.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "tharp_narrow_range_breakout"
SOURCES = ("Van K. Tharp — Trade Your Way to Financial Freedom",)
KEYS = (
    "tharp_trend_direction",
    "tharp_range_ratio",
    "tharp_inside_day",
    "tharp_narrowest_range",
    "tharp_breakout_direction",
    "tharp_entry_confirmation",
    "tharp_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present"}


def _direction(value) -> str | None:
    value = normalized_status(value)
    if value in {"buy", "long", "up", "bull", "bullish"}:
        return "BUY"
    if value in {"sell", "short", "down", "bear", "bearish"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("trend_compression_timing",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = first(state, "tharp_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "journal")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["tharp_data_provenance"]
        result["reasons"] = ["the setup requires an observed timestamped range study"]
        return result

    trend = _direction(first(state, "tharp_trend_direction"))
    breakout = _direction(first(state, "tharp_breakout_direction"))
    ratio = number(first(state, "tharp_range_ratio"))
    if ratio is not None and ratio < 0:
        result["view"] = "WAIT"
        result["tharp_narrow_range_assessment"] = "INVALID_RANGE_RATIO"
        result["reasons"] = ["range ratio cannot be negative"]
        return result
    compressed = (ratio is not None and ratio <= 0.60) or (
        _truth(first(state, "tharp_inside_day"))
        and _truth(first(state, "tharp_narrowest_range"))
    )
    if trend is None:
        result["view"] = "WAIT"
        result["tharp_narrow_range_assessment"] = "TREND_NOT_CONFIRMED"
        result["reasons"] = ["narrow-range setup requires a recorded market direction"]
        return result
    if not compressed:
        result["view"] = "WAIT"
        result["tharp_narrow_range_assessment"] = "COMPRESSION_NOT_CONFIRMED"
        result["reasons"] = ["range compression is neither at or below the 60% example nor an inside narrowest range"]
        return result
    if not explicitly_confirmed(first(state, "tharp_entry_confirmation")) and not _truth(first(state, "tharp_entry_confirmation")):
        result["view"] = "WAIT"
        result["tharp_narrow_range_assessment"] = "TIMING_NOT_CONFIRMED"
        result["reasons"] = ["compression is a setup and still needs a confirmed directional timing trigger"]
        return result
    if breakout is None or breakout != trend:
        result["view"] = "WAIT"
        result["tharp_narrow_range_assessment"] = "BREAKOUT_DIRECTION_CONFLICT"
        result["reasons"] = ["the timing trigger does not agree with the established trend"]
        return result
    result["tharp_narrow_range_assessment"] = "CONFIRMED_SETUP"
    result["tharp_range_ratio"] = ratio
    return with_direction(result, state, breakout, "trend, narrow-range compression, and same-direction entry timing are observed")
