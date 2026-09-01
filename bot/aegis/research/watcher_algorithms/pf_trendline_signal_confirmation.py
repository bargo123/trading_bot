"""Jeremy du Plessis' Point-and-Figure trendline-break confirmation rule."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "pf_trendline_signal_confirmation"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 176-178"
KEYS = (
    "pf_trendline_trend",
    "pf_trendline_signal_direction",
    "pf_trendline_signal_timing",
    "pf_trendline_break_confirmed",
    "pf_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pf_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not _truthy(first(state, "pf_trendline_break_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the Point-and-Figure trendline break is not confirmed"]
        return result
    trend = normalized_status(first(state, "pf_trendline_trend"))
    signal = normalized_status(first(state, "pf_trendline_signal_direction"))
    timing = normalized_status(first(state, "pf_trendline_signal_timing")).replace(" ", "_")
    if trend not in {"up", "down"} or signal not in {"up", "down"}:
        result["view"] = "WAIT"
        result["reasons"] = ["trendline and signal directions must be explicit"]
        return result
    if timing not in {"at_break", "within_one_box_before", "within_two_boxes_before", "after_break"}:
        result["view"] = "WAIT"
        result["reasons"] = ["a trendline break needs a Point-and-Figure signal at, near before, or after the break"]
        return result
    expected_signal = "up" if trend == "down" else "down"
    if signal != expected_signal:
        result["view"] = "WAIT"
        result["reasons"] = ["trendline break and Point-and-Figure signal do not point in the same direction"]
        return result
    result["pf_trendline_signal_timing"] = timing
    return with_direction(
        result,
        state,
        "BUY" if signal == "up" else "SELL",
        "confirmed Point-and-Figure trendline break has a nearby matching signal",
    )
