"""John Carter's pivot pullback play with trending/choppy-day geometry."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "carter_pivot_play"
SOURCES = ("John F. Carter — Mastering the Trade",)
KEYS = (
    "carter_pivot_market",
    "carter_pivot_level",
    "carter_pivot_entry_price",
    "carter_pivot_next_level",
    "carter_pivot_next_next_level",
    "carter_pivot_day_type",
    "carter_pivot_five_min_volume",
    "carter_pivot_quarterway_advance",
    "carter_pivot_gap_playable",
    "carter_pivot_pullback_confirmed",
    "carter_pivot_minutes_et",
    "carter_pivot_consecutive_hard_losses",
    "carter_pivot_data_provenance",
)
MARKETS = {"es", "ym", "nq", "tf", "stock"}
ENTRY_OFFSETS = {"ym": 3.0, "es": 0.25, "nq": 0.50, "tf": 0.20, "stock": 0.05}
STOP_POINTS = {"ym": 20.0, "es": 2.0, "nq": 4.0, "tf": 1.50}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "carter_pivot_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("carter_pivot_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    market = normalized_status(first(state, "carter_pivot_market")).replace(" ", "")
    if market not in MARKETS:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["the pivot geometry is not mapped to this observed instrument"]
        return result
    candidate_side = side(state)
    level = number(first(state, "carter_pivot_level"))
    entry = number(first(state, "carter_pivot_entry_price"))
    next_level = number(first(state, "carter_pivot_next_level"))
    next_next = number(first(state, "carter_pivot_next_next_level"))
    minutes = number(first(state, "carter_pivot_minutes_et"))
    volume = number(first(state, "carter_pivot_five_min_volume"))
    losses = number(first(state, "carter_pivot_consecutive_hard_losses"))
    if candidate_side not in {"BUY", "SELL"} or any(value is None for value in (level, entry, next_level, next_next, minutes, volume, losses)):
        result["reasons"] = ["side, pivot levels, entry, volume, time, and loss count must be finite observations"]
        return result
    if not 0 <= minutes < 1440:
        result["reasons"] = ["the pivot timestamp must be a valid ET minute"]
        return result
    if first(state, "carter_pivot_gap_playable") is False and minutes < 585:
        result["reasons"] = ["without a playable opening gap the first pivot play waits until 9:45 ET"]
        return result
    if volume > 25000 and first(state, "carter_pivot_quarterway_advance") is not True:
        result["reasons"] = ["heavy five-minute ES volume requires a quarter-way advance before the first retracement"]
        return result
    if first(state, "carter_pivot_pullback_confirmed") is not True:
        result["reasons"] = ["the observed entry is not a confirmed retracement to the violated pivot"]
        return result
    if losses >= 2:
        result["reasons"] = ["two consecutive hard-stop pivot losses end the source setup for the day"]
        return result
    offset = entry - level
    expected = ENTRY_OFFSETS[market]
    signed_expected = expected if candidate_side == "BUY" else -expected
    if abs(offset - signed_expected) > max(1e-9, expected * 0.05):
        result["reasons"] = ["the entry is not just in front of the pivot by the source market-specific offset"]
        return result
    day_type = normalized_status(first(state, "carter_pivot_day_type"))
    if day_type not in {"trending", "choppy"}:
        result["reasons"] = ["pivot targets require an observed trending or choppy day classification"]
        return result
    stop_points = STOP_POINTS.get(market)
    if market == "stock":
        stop_points = number(first(state, "carter_pivot_stock_stop_points"))
    if stop_points is None or stop_points <= 0:
        result["reasons"] = ["stock pivot plays require observed price-scaled stop geometry"]
        return result
    result.update({
        "carter_pivot_entry_offset_points": abs(offset),
        "carter_pivot_stop_points": stop_points,
        "carter_pivot_first_target": next_level if candidate_side == "BUY" else next_level,
        "carter_pivot_second_target": next_next if candidate_side == "BUY" else next_next,
        "carter_pivot_day_type": day_type,
    })
    return with_direction(result, state, candidate_side, "the observed limit entry is a source-style retracement just in front of a pivot")
