"""Brian Anderson's one-triggers-all breakout bracket perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "anderson_conditional_bracket"
SOURCES = ("Brian Anderson — The 1 Hour Trade",)
KEYS = (
    "anderson_first_15m_high",
    "anderson_entry_stop_price",
    "anderson_entry_limit_price",
    "anderson_pullback_low",
    "anderson_stop_price",
    "anderson_tick_size",
    "anderson_entry_buffer_ticks",
    "anderson_order_type",
    "anderson_bracket_type",
    "anderson_stop_order_type",
    "anderson_stop_reference",
    "anderson_data_provenance",
)


def _truth(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed"}


def evaluate(state):
    found = values(state, *KEYS)
    high = number(first(state, "anderson_first_15m_high"))
    entry_stop = number(first(state, "anderson_entry_stop_price"))
    entry_limit = number(first(state, "anderson_entry_limit_price"))
    pullback_low = number(first(state, "anderson_pullback_low"))
    stop = number(first(state, "anderson_stop_price"))
    tick = number(first(state, "anderson_tick_size"))
    buffer_ticks = number(first(state, "anderson_entry_buffer_ticks"))
    missing = [
        key
        for key, value in (
            ("anderson_first_15m_high", high),
            ("anderson_entry_stop_price", entry_stop),
            ("anderson_entry_limit_price", entry_limit),
            ("anderson_pullback_low", pullback_low),
            ("anderson_stop_price", stop),
            ("anderson_tick_size", tick),
            ("anderson_entry_buffer_ticks", buffer_ticks),
            ("anderson_order_type", first(state, "anderson_order_type")),
            ("anderson_bracket_type", first(state, "anderson_bracket_type")),
            ("anderson_stop_order_type", first(state, "anderson_stop_order_type")),
            ("anderson_stop_reference", first(state, "anderson_stop_reference")),
        )
        if value is None or value == ""
    ]
    provenance = first(state, "anderson_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        missing.append("anderson_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "side")) != "buy":
        result["reasons"] = ["the source high-volume runner bracket is a long breakout setup"]
        return result
    if any(value is None or value <= 0 for value in (high, entry_stop, entry_limit, pullback_low, tick)):
        result["reasons"] = ["bracket prices and tick size must be positive observations"]
        return result
    if buffer_ticks != 1 or entry_stop != high + tick * buffer_ticks:
        result["reasons"] = ["the stop-limit trigger must be one tick above the first-fifteen-minute high"]
        return result
    if normalized_status(first(state, "anderson_order_type")) != "stop limit":
        result["reasons"] = ["the source requires a stop-limit entry order"]
        return result
    if normalized_status(first(state, "anderson_bracket_type")) != "one triggers all":
        result["reasons"] = ["the entry and protective stop must be linked as one-triggers-all"]
        return result
    if normalized_status(first(state, "anderson_stop_order_type")) != "stop on quote":
        result["reasons"] = ["the source protective leg is a stop-on-quote order"]
        return result
    if normalized_status(first(state, "anderson_stop_reference")) != "opening range pullback low":
        result["reasons"] = ["the preferred source stop reference is the opening-range pullback low"]
        return result
    if stop >= pullback_low or stop >= entry_stop or entry_limit <= 0:
        result["reasons"] = ["the protective stop must be below the observed opening-range pullback low"]
        return result
    result["anderson_order_action"] = "ARM_CONDITIONAL_BRACKET"
    result["anderson_entry_stop_price"] = entry_stop
    result["anderson_entry_limit_price"] = entry_limit
    result["anderson_protective_stop_price"] = stop
    return with_direction(result, state, "BUY", "the observed opening-range breakout bracket has a linked protective stop")
