"""The Holy Grail appendix's paired-stop lifecycle, as a read-only study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "grail_bracket_lifecycle"
SOURCES = ("James Windsor — The Holy Grail Forex Trading System",)
KEYS = (
    "grail_reference_pair",
    "grail_anchor_time",
    "grail_anchor_price",
    "grail_buy_stop_price",
    "grail_sell_stop_price",
    "grail_pip_size",
    "grail_stop_pips",
    "grail_target_pips",
    "grail_trailing_stop_pips",
    "grail_lifecycle_event",
    "grail_opposite_order_deleted",
    "grail_lifecycle_provenance",
)


def _truth(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed"}


def evaluate(state):
    found = values(state, *KEYS)
    anchor = number(first(state, "grail_anchor_price"))
    pip = number(first(state, "grail_pip_size"))
    buy_stop = number(first(state, "grail_buy_stop_price"))
    sell_stop = number(first(state, "grail_sell_stop_price"))
    missing = [
        key
        for key, value in (
            ("grail_reference_pair", first(state, "grail_reference_pair")),
            ("grail_anchor_time", first(state, "grail_anchor_time")),
            ("grail_anchor_price", anchor),
            ("grail_buy_stop_price", buy_stop),
            ("grail_sell_stop_price", sell_stop),
            ("grail_pip_size", pip),
            ("grail_stop_pips", number(first(state, "grail_stop_pips"))),
            ("grail_target_pips", number(first(state, "grail_target_pips"))),
            ("grail_trailing_stop_pips", number(first(state, "grail_trailing_stop_pips"))),
            ("grail_lifecycle_event", first(state, "grail_lifecycle_event")),
            ("grail_opposite_order_deleted", first(state, "grail_opposite_order_deleted")),
        )
        if value is None or value == ""
    ]
    provenance = first(state, "grail_lifecycle_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "journal")):
        missing.append("grail_lifecycle_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "grail_reference_pair")) != "gbpusd":
        result["reasons"] = ["the appendix paired-stop rule is specified for GBPUSD only"]
        return result
    if normalized_status(first(state, "grail_anchor_time")) != "08:00 uk":
        result["reasons"] = ["the paired orders were not anchored at exactly 08:00 UK"]
        return result
    if any(value is None or value <= 0 for value in (anchor, pip)):
        result["reasons"] = ["anchor price and pip size must be positive observations"]
        return result
    if any(number(first(state, key)) != expected for key, expected in (
        ("grail_stop_pips", 80.0),
        ("grail_target_pips", 240.0),
        ("grail_trailing_stop_pips", 60.0),
    )):
        result["reasons"] = ["the baseline appendix stop, target, and trailing values are not exact"]
        return result
    if buy_stop != anchor + 40.0 * pip or sell_stop != anchor - 40.0 * pip:
        result["reasons"] = ["the symmetric buy-stop and sell-stop levels are not 40 pips from the anchor"]
        return result

    event = normalized_status(first(state, "grail_lifecycle_event"))
    result["grail_bracket_levels"] = {"buy_stop": buy_stop, "sell_stop": sell_stop}
    result["grail_source_geometry"] = {"stop_pips": 80.0, "target_pips": 240.0, "trailing_stop_pips": 60.0}
    if event == "armed":
        result["grail_lifecycle_action"] = "BRACKET_ARMED"
        result["reasons"] = ["both source stop orders are armed from the observed 08:00 UK anchor"]
        return result
    if event in {"buy triggered", "sell triggered"}:
        if not _truth(first(state, "grail_opposite_order_deleted")):
            result["reasons"] = ["the source requires deletion of the opposite pending order after a trigger"]
            return result
        signal = "BUY" if event == "buy triggered" else "SELL"
        result["grail_lifecycle_action"] = "DELETE_OPPOSITE_ORDER"
        return with_direction(result, state, signal, "one bracket side triggered and the opposite pending order was deleted")
    if event == "time close":
        if normalized_status(first(state, "grail_current_uk_time")) != "18:00 uk":
            result["reasons"] = ["the source session-close event is not observed at 18:00 UK"]
            return result
        result["grail_lifecycle_action"] = "CLOSE_ALL_AT_SESSION_BOUNDARY"
        result["reasons"] = ["the source requires all trades to close at the 18:00 UK boundary"]
        return result
    result["reasons"] = ["the Grail lifecycle event is not an observed armed, trigger, or time-close state"]
    return result
