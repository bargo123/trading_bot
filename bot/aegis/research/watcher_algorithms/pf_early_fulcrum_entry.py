"""Jeremy du Plessis' early low-risk Point-and-Figure fulcrum entry."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_early_fulcrum_entry"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 332-333"
KEYS = (
    "pf_fulcrum_trend",
    "pf_fulcrum_new_extreme",
    "pf_early_reaction_boxes",
    "pf_early_stop_boxes",
    "pf_early_entry_confirmed",
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
    trend = normalized_status(first(state, "pf_fulcrum_trend"))
    extreme = normalized_status(first(state, "pf_fulcrum_new_extreme")).replace(" ", "_")
    reaction = number(first(state, "pf_early_reaction_boxes"))
    stop = number(first(state, "pf_early_stop_boxes"))
    if trend not in {"up", "down"} or extreme not in {"lower_low", "higher_high"}:
        result["view"] = "WAIT"
        result["reasons"] = ["fulcrum trend and new extreme must be explicit"]
        return result
    if reaction is None or reaction < 2 or reaction != int(reaction) or stop is None or stop != 1:
        result["view"] = "WAIT"
        result["reasons"] = ["the early entry needs a two-box reaction and a one-box protective stop"]
        return result
    expected_extreme = "lower_low" if trend == "up" else "higher_high"
    if extreme != expected_extreme:
        result["view"] = "WAIT"
        result["reasons"] = ["new extreme does not agree with the fulcrum direction"]
        return result
    if not _truthy(first(state, "pf_early_entry_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the early fulcrum reaction is not confirmed"]
        return result
    result["pf_early_entry_assessment"] = "CONFIRMED"
    result["pf_early_reaction_boxes"] = int(reaction)
    return with_direction(result, state, "BUY" if trend == "up" else "SELL", "confirmed early fulcrum entry with one-box stop geometry")
