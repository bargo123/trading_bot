"""Price-in-Time European double-open no-trading-zone breakout perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "price_in_time_ntz_breakout"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "pit_session",
    "pit_ntz_width_pips",
    "pit_breakout_direction",
    "pit_breakout_confirmation",
    "pit_inside_ntz",
    "pit_anomalous_day",
    "pit_data_provenance",
)


def _missing(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pit_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pit_data_provenance")
    return list(dict.fromkeys(missing))


def _london_after_open(value) -> bool:
    session = normalized_status(value)
    if not session or any(token in session for token in ("inside ntz", "before london", "asian", "after 1700", "new york close")):
        return False
    return session in {
        "london after 0800 gmt",
        "london morning after 0800 gmt",
        "london morning",
    } or ("london" in session and "after" in session and "0800" in session)


def evaluate(state):
    missing = _missing(state)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    width = number(first(state, "pit_ntz_width_pips"))
    if width is None or not 10.0 <= width <= 30.0:
        result["view"] = "WAIT"
        result["reasons"] = ["the European no-trading-zone width must be between 10 and 30 pips"]
        return result
    if not _london_after_open(first(state, "pit_session")):
        result["view"] = "WAIT"
        result["reasons"] = ["the source breakout is evaluated only after the London 08:00 GMT open"]
        return result
    if volman_truth(first(state, "pit_inside_ntz")):
        result["view"] = "WAIT"
        result["reasons"] = ["price remains inside the no-trading zone"]
        return result
    anomaly_value = first(state, "pit_anomalous_day")
    anomaly = normalized_status(anomaly_value)
    anomaly_cleared = anomaly_value is False or anomaly in {
        "false",
        "no",
        "not anomalous",
        "not anomalous quote range proxy",
    }
    if volman_truth(anomaly_value) or not anomaly_cleared:
        result["view"] = "WAIT"
        result["reasons"] = ["the source excludes an anomalous day, but the Asian-move exclusion is not cleared"]
        return result
    if not volman_truth(first(state, "pit_breakout_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["the no-trading-zone break has not been confirmed"]
        return result
    breakout = normalized_status(first(state, "pit_breakout_direction"))
    if breakout == "up":
        return with_direction(result, state, "BUY", "confirmed break above the London no-trading-zone high")
    if breakout == "down":
        return with_direction(result, state, "SELL", "confirmed break below the London no-trading-zone low")
    result["view"] = "WAIT"
    result["reasons"] = ["no-trading-zone breakout direction is unresolved"]
    return result
