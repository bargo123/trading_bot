"""John Carter's 3:52/end-of-day futures fade study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "carter_end_of_day_fade"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_eod_market",
    "carter_eod_minutes_et",
    "carter_eod_price_at_1530",
    "carter_eod_price_at_entry",
    "carter_eod_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_eod_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_eod_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    market = normalized_status(first(state, "carter_eod_market")).replace(" ", "")
    if market not in {"es", "ym"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the 3:52 play is defined for observed ES or YM futures"]
        return result
    minutes = number(first(state, "carter_eod_minutes_et"))
    reference = number(first(state, "carter_eod_price_at_1530"))
    entry = number(first(state, "carter_eod_price_at_entry"))
    if any(value is None for value in (minutes, reference, entry)):
        result["view"] = "WAIT"
        result["reasons"] = ["the 3:30 reference, 3:52 entry, and ET time must be finite observations"]
        return result
    if minutes != 952:
        result["view"] = "WAIT"
        result["reasons"] = ["the source trigger is the opening of the 3:52 ET one-minute bar"]
        return result
    minimum_move = 1.0 if market == "es" else 10.0
    move = entry - reference
    if abs(move) < minimum_move:
        result["view"] = "WAIT"
        result["reasons"] = ["the 3:30-to-3:52 move is below the source market-specific minimum"]
        return result
    signal = "SELL" if move > 0 else "BUY"
    result["carter_eod_move_points"] = move
    result["carter_eod_stop_points"] = 2.0 if market == "es" else 20.0
    result["carter_exit_minutes_et"] = 973.0
    result["carter_hold_minutes"] = 21.0
    return with_direction(result, state, signal, "the source fades a qualifying 3:30-to-3:52 move at the exact time trigger")
