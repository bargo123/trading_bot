"""Cartea--Jaimungal immediate cancellation rule for stale resting quotes."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "cartea_quote_freshness_guard"
SOURCES = ("Modelling Asset Prices for Algorithmic and High-Frequency Trading",)
KEYS = (
    "cartea_quote_created_time_s",
    "cartea_now_time_s",
    "cartea_last_trade_time_s",
    "cartea_last_state_change_time_s",
    "cartea_quote_max_age_s",
    "cartea_quote_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "cartea_quote_data_provenance"),
        accepted=("observed", "timestamped", "quote"),
    ):
        missing.append("cartea_quote_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    created = number(first(state, "cartea_quote_created_time_s"))
    now = number(first(state, "cartea_now_time_s"))
    last_trade = number(first(state, "cartea_last_trade_time_s"))
    last_change = number(first(state, "cartea_last_state_change_time_s"))
    max_age = number(first(state, "cartea_quote_max_age_s"))
    if (
        None in {created, now, last_trade, last_change, max_age}
        or max_age <= 0
        or now < created
        or last_trade > now
        or last_change > now
    ):
        result["cartea_quote_assessment"] = "INVALID_QUOTE_TIMELINE"
        result["reasons"] = ["quote and event timestamps must be finite, ordered, and not from the future"]
        return result

    stale_reasons = []
    age = now - created
    if age > max_age:
        stale_reasons.append("quote_age_exceeded")
    if last_trade > created:
        stale_reasons.append("trade_arrived_after_quote")
    if last_change > created:
        stale_reasons.append("market_state_changed_after_quote")
    result["cartea_quote_age_s"] = age
    result["cartea_quote_stale_reasons"] = stale_reasons
    result["cartea_quote_assessment"] = "QUOTE_STALE" if stale_reasons else "QUOTE_FRESH"
    result["cartea_cancel_immediately"] = bool(stale_reasons)
    result["reasons"] = [
        "a resting quote is stale after its age limit, a subsequent trade, or an observed market-state transition"
    ]
    return result
