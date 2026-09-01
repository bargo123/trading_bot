"""Level-2 order-book imbalance perspective; tick proxies are rejected."""
from __future__ import annotations

from ._common import base, explicitly_observed, first, number, text, values, with_direction

ALGORITHM_ID = "order_book_imbalance"
SOURCES = (
    "Trades, Quotes and Prices — Bouchaud, Bonart, Donier, Gould",
    "Empirical Market Microstructure — Joel Hasbrouck",
    "High-Frequency Trading — Irene Aldridge",
)
KEYS = ("order_book_imbalance", "depth_levels", "order_book_age_s", "order_book_data_provenance", "bid_depth", "ask_depth")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("level_2_order_book",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = text(first(state, "order_book_data_provenance")).lower()
    if not provenance:
        result["view"] = "MISSING_DATA"
        result["applicability"] = "MISSING_DATA"
        result["missing_inputs"] = ["order_book_data_provenance"]
        result["reasons"] = ["order-book imbalance has no provenance"]
        return result
    if not explicitly_observed(provenance, accepted=("real", "depth", "l2", "level")) or any(token in provenance for token in ("tick", "quote")):
        result["view"] = "WAIT"
        result["warnings"] = ["tick/quote imbalance is not a level-2 order-book measurement"]
        result["reasons"] = ["real depth provenance is not established"]
        return result
    age = number(first(state, "order_book_age_s"))
    if age is not None and age > 5:
        result["view"] = "WAIT"
        result["reasons"] = ["level-2 snapshot is stale"]
        return result
    imbalance = number(first(state, "order_book_imbalance"))
    if imbalance is None:
        result["view"] = "MISSING_DATA"
        result["applicability"] = "MISSING_DATA"
        result["missing_inputs"] = ["order_book_imbalance"]
        result["reasons"] = ["level-2 provenance exists without a numeric imbalance"]
    elif imbalance > 0:
        return with_direction(result, state, "BUY", "real level-2 depth imbalance favors bids")
    elif imbalance < 0:
        return with_direction(result, state, "SELL", "real level-2 depth imbalance favors offers")
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["level-2 depth is balanced"]
    return result
