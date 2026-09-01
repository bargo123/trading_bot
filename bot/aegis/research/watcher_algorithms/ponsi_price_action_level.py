"""Ponsi's price-action-before-entry filter at support or resistance."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, ponsi_missing, values, with_direction

ALGORITHM_ID = "ponsi_price_action_level"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "side",
    "ponsi_price_level",
    "ponsi_approach_speed",
    "ponsi_price_action",
    "ponsi_entry_order_location",
    "ponsi_level_test_count",
    "ponsi_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = ponsi_missing(state, KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    level = normalized_status(first(state, "ponsi_price_level"))
    approach = normalized_status(first(state, "ponsi_approach_speed"))
    action = normalized_status(first(state, "ponsi_price_action"))
    entry_location = normalized_status(first(state, "ponsi_entry_order_location"))
    tests = number(first(state, "ponsi_level_test_count"))
    if level not in {"support", "resistance"} or tests is None or tests < 1:
        result["ponsi_price_action_assessment"] = "LEVEL_OBSERVATION_INVALID"
        result["reasons"] = ["a valid support/resistance area and at least one observed test are required"]
        return result
    if approach in {"fast", "rushing", "rapid", "freight train"}:
        result["ponsi_price_action_assessment"] = "FREIGHT_TRAIN_APPROACH"
        result["reasons"] = ["Ponsi advises stepping aside when price rushes into the level without readable price action"]
        return result
    accepted_action = {"rejection", "bounce", "holding", "confirmed", "confirmed rejection"}
    expected_location = "above support" if level == "support" else "below resistance"
    if action not in accepted_action or entry_location != expected_location:
        result["ponsi_price_action_assessment"] = "REACTION_OR_ENTRY_ORDER_MISSING"
        result["reasons"] = ["the level reaction and the source-defined conditional entry location are not confirmed"]
        return result
    signal = "BUY" if level == "support" else "SELL"
    result["ponsi_price_action_assessment"] = "CONFIRMED_LEVEL_REACTION"
    return with_direction(result, state, signal, "price action was observed at the level before placing the conditional entry")
