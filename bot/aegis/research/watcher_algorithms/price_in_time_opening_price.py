"""Price-in-Time European opening-price sentiment boundary."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "price_in_time_opening_price"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "side",
    "pit_europe_open_price",
    "pit_current_price",
    "pit_opening_price_relation",
    "pit_opening_cross_direction",
    "pit_opening_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    required = {
        "side": first(state, "side"),
        "pit_europe_open_price": number(first(state, "pit_europe_open_price")),
        "pit_current_price": number(first(state, "pit_current_price")),
        "pit_opening_price_relation": normalized_status(first(state, "pit_opening_price_relation")),
        "pit_opening_cross_direction": normalized_status(first(state, "pit_opening_cross_direction")),
    }
    missing = [key for key, value in required.items() if value is None or value == ""]
    if not explicitly_observed(first(state, "pit_opening_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("pit_opening_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    opening = required["pit_europe_open_price"]
    current = required["pit_current_price"]
    relation = required["pit_opening_price_relation"]
    cross = required["pit_opening_cross_direction"]
    if opening <= 0 or current <= 0 or relation not in {"above", "below", "at"} or cross not in {"up", "down", "none", "no cross"}:
        result["view"] = "WAIT"
        result["reasons"] = ["opening-price evidence contains an invalid relation or crossing state"]
        return result
    if relation == "above" and cross == "up":
        result["pit_opening_assessment"] = "UPWARD_OPENING_BREAK"
        return with_direction(result, state, "BUY", "price has crossed above the observed European opening level")
    if relation == "below" and cross == "down":
        result["pit_opening_assessment"] = "DOWNWARD_OPENING_BREAK"
        return with_direction(result, state, "SELL", "price has crossed below the observed European opening level")
    result["pit_opening_assessment"] = "NO_ACTIONABLE_OPENING_BREAK"
    result["view"] = "WAIT"
    result["reasons"] = ["the source uses a fresh cross of the European opening level; no aligned cross is observed"]
    return result
