"""John Carter's 8/21 EMA pullback propulsion study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_ema_propulsion"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_propulsion_instrument",
    "carter_propulsion_timeframe",
    "carter_ema_fast",
    "carter_ema_slow",
    "carter_entry_price",
    "carter_pullback_to_fast",
    "carter_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    instrument = normalized_status(first(state, "carter_propulsion_instrument")).replace(" ", "_")
    timeframe = normalized_status(first(state, "carter_propulsion_timeframe"))
    fast = number(first(state, "carter_ema_fast"))
    slow = number(first(state, "carter_ema_slow"))
    entry = number(first(state, "carter_entry_price"))
    if instrument not in {"stock", "index_future"} or timeframe not in {"daily", "60m", "60_minute", "60_min"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the source propulsion rules are defined for daily or 60-minute stock/index-future charts"]
        return result
    if any(value is None for value in (fast, slow, entry)) or entry <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["EMA and entry observations must be finite and positive"]
        return result
    if not _truthy(first(state, "carter_pullback_to_fast")):
        result["view"] = "WAIT"
        result["reasons"] = ["price has not made the source pullback to the fast EMA"]
        return result
    side = (first(state, "side") or "").upper()
    if fast > slow:
        signal = "BUY"
    elif fast < slow:
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the 8/21 EMA trend is not separated"]
        return result
    if side in {"BUY", "SELL"} and side != signal:
        result["view"] = "WAIT"
        result["reasons"] = ["the candidate side fights the 8/21 EMA direction"]
        return result
    if instrument == "stock":
        target_pct, stop_pct, watermark_pct = 0.08, 0.04, 4.0
    elif timeframe == "daily":
        target_pct, stop_pct, watermark_pct = 0.01, 0.005, None
    else:
        target_pct, stop_pct, watermark_pct = 0.005, 0.0025, None
    ema_distance = abs(entry - slow)
    stop_distance = max(entry * stop_pct, ema_distance)
    if signal == "BUY":
        target = entry * (1 + target_pct)
        stop = entry - stop_distance
    else:
        target = entry * (1 - target_pct)
        stop = entry + stop_distance
    result["carter_target_price"] = target
    result["carter_initial_stop"] = stop
    result["carter_watermark_percent"] = watermark_pct
    result["carter_fast_ema_pullback"] = fast
    if first(state, "carter_weekly_ema_alignment") is False or normalized_status(first(state, "carter_weekly_ema_alignment")) in {"false", "no", "against"}:
        result["warnings"] = ["optional weekly 8/21 EMA alignment does not support the daily setup"]
    return with_direction(result, state, signal, "8/21 EMA direction and pullback-to-fast-EMA entry align")
