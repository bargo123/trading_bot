"""Price-in-Time session-window filter."""
from __future__ import annotations

from ._common import absent, base, first, explicitly_observed, normalized_status, values

ALGORITHM_ID = "price_in_time_session_filter"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = ("pit_session_window", "pit_session_data_provenance")

_ALLOWED = {"london morning", "london morning 0800 1300", "london new york overlap", "american morning"}
_EXCLUDED = {"asian", "frankfurt ntz", "post london", "american afternoon", "outside source window"}


def evaluate(state):
    found = values(state, *KEYS)
    window = normalized_status(first(state, "pit_session_window"))
    missing = []
    if not window:
        missing.append("pit_session_window")
    if not explicitly_observed(first(state, "pit_session_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("pit_session_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if window in _ALLOWED:
        result["pit_session_assessment"] = "TRADE_WINDOW"
        result["pit_session_action"] = "ALLOW_SOURCE_WINDOW"
        result["reasons"] = ["the observed GMT window is within the source's European/American morning trading hours"]
        return result
    if window in _EXCLUDED:
        result["pit_session_assessment"] = "EXCLUDE_SESSION"
        result["pit_session_action"] = "NO_TRADE"
        result["reasons"] = ["the source excludes the Asian, pre-London, or post-London low-liquidity window"]
        return result
    result["pit_session_assessment"] = "UNKNOWN_SESSION"
    result["pit_session_action"] = "NO_TRADE"
    result["view"] = "MISSING_DATA"
    result["applicability"] = "MISSING_DATA"
    result["missing_inputs"] = ["recognized_pit_session_window"]
    result["reasons"] = ["the copied session label is not one of the source-defined windows"]
    return result
