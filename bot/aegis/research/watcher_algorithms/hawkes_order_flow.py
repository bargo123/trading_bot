"""Validated Hawkes-style buy/sell event-intensity perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_validated, first, number, strings, values, with_direction

ALGORITHM_ID = "hawkes_order_flow"
SOURCES = (
    "Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",
    "Jean-Philippe Bouchaud et al. — Trades, Quotes and Prices",
)
KEYS = (
    "hawkes_buy_intensity", "hawkes_sell_intensity", "hawkes_model_status",
    "hawkes_confirmation", "hawkes_observation_n", "hawkes_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_order_event_intensities",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    buy = number(first(state, "hawkes_buy_intensity"))
    sell = number(first(state, "hawkes_sell_intensity"))
    status = first(state, "hawkes_model_status")
    confirmation = first(state, "hawkes_confirmation")
    validated = explicitly_validated(status, accepted=("validated", "walk forward", "sealed oos"))
    confirmed = explicitly_confirmed(confirmation)
    if None in {buy, sell} or buy < 0 or sell < 0 or not validated or not confirmed:
        result["view"] = "WAIT"
        result["reasons"] = ["Hawkes order-flow signal requires validated intensities and confirmation"]
        return result
    if buy > sell:
        return with_direction(result, state, "BUY", "validated buy-event intensity exceeds sell-event intensity")
    if sell > buy:
        return with_direction(result, state, "SELL", "validated sell-event intensity exceeds buy-event intensity")
    result["view"] = "WAIT"
    result["reasons"] = ["buy and sell event intensities are equal"]
    return result
