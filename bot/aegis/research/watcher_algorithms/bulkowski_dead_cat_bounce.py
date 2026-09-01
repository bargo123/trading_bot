"""Bulkowski dead-cat bounce: negative event, temporary bounce, second decline."""
from __future__ import annotations

from ._common import first, number
from .bulkowski_pattern_common import direction, finish, observed_bool, start

ALGORITHM_ID = "bulkowski_dead_cat_bounce"
SOURCES = ("Thomas N. Bulkowski — Encyclopedia of Chart Patterns",)
SOURCE_PAGES = "829-843"
KEYS = (
    "bulkowski_dcb_negative_event_confirmed", "bulkowski_dcb_price_gap_down_confirmed",
    "bulkowski_dcb_plunge_pct", "bulkowski_dcb_bounce_pct", "bulkowski_dcb_postbounce_decline_pct",
    "bulkowski_dcb_plunge_days", "bulkowski_dcb_bounce_days", "bulkowski_dcb_decline_days",
    "bulkowski_dcb_event_high", "bulkowski_dcb_event_low", "bulkowski_dcb_bounce_high",
    "bulkowski_dcb_current_price", "bulkowski_dcb_decline_confirmed",
    "bulkowski_dcb_signal_direction", "bulkowski_data_provenance",
)


def evaluate(state):
    result = start(ALGORITHM_ID, state, KEYS)
    if result["view"] == "MISSING_DATA":
        return result
    values = {key: number(first(state, key)) for key in (
        "bulkowski_dcb_plunge_pct", "bulkowski_dcb_bounce_pct", "bulkowski_dcb_postbounce_decline_pct",
        "bulkowski_dcb_plunge_days", "bulkowski_dcb_bounce_days", "bulkowski_dcb_decline_days",
        "bulkowski_dcb_event_high", "bulkowski_dcb_event_low", "bulkowski_dcb_bounce_high",
        "bulkowski_dcb_current_price",
    )}
    signal = direction(state, "bulkowski_dcb_signal_direction")
    if not all(observed_bool(first(state, key)) for key in ("bulkowski_dcb_negative_event_confirmed", "bulkowski_dcb_price_gap_down_confirmed")):
        result["reasons"] = ["a dead-cat bounce requires an observed negative event and downward price gap"]
        return result
    if any(value is None for value in values.values()) or signal is None:
        result["reasons"] = ["dead-cat bounce event, phase durations, and prices must be finite observations"]
        return result
    if not 15 <= values["bulkowski_dcb_plunge_pct"] <= 80 or not 15 <= values["bulkowski_dcb_bounce_pct"] <= 35 or not 15 <= values["bulkowski_dcb_postbounce_decline_pct"] <= 45:
        result["reasons"] = ["the event plunge, temporary bounce, and second decline do not match the observed dead-cat ranges"]
        return result
    if not 1 <= values["bulkowski_dcb_plunge_days"] <= 8 or not 5 <= values["bulkowski_dcb_bounce_days"] <= 25 or not 10 <= values["bulkowski_dcb_decline_days"] <= 50:
        result["reasons"] = ["dead-cat bounce phase durations are outside the observed pattern ranges"]
        return result
    if values["bulkowski_dcb_event_high"] <= values["bulkowski_dcb_event_low"] or values["bulkowski_dcb_bounce_high"] <= values["bulkowski_dcb_event_low"] or values["bulkowski_dcb_current_price"] >= values["bulkowski_dcb_bounce_high"]:
        result["reasons"] = ["the dead-cat bounce needs a lower event, a temporary recovery, and a current second decline"]
        return result
    if signal != "DOWN" or not observed_bool(first(state, "bulkowski_dcb_decline_confirmed")):
        result["reasons"] = ["the post-bounce decline is not confirmed as the active bearish phase"]
        return result
    depth = values["bulkowski_dcb_event_high"] - values["bulkowski_dcb_event_low"]
    result.update({"source_pages": SOURCE_PAGES, "bulkowski_dcb_depth": depth, "bulkowski_measure_target": values["bulkowski_dcb_current_price"] - depth, "bulkowski_stop_price": values["bulkowski_dcb_bounce_high"]})
    return finish(result, state, "SELL", "a negative event gap was followed by a temporary bounce and confirmed second decline")
