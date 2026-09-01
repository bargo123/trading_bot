"""Inventory-aware market-making perspective; never submits or manages orders."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "market_making_inventory"
SOURCES = (
    "Irene Aldridge — High-Frequency Trading",
    "Maureen O'Hara — Market Microstructure Theory",
    "Jean-Philippe Bouchaud et al. — Trades, Quotes and Prices",
)
KEYS = ("market_maker_signal", "inventory_state", "microprice", "mid_price", "spread")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("inventory_and_microprice_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = str(first(state, "market_maker_signal") or "").strip().upper()
    inventory = strings(state, "inventory_state")
    microprice = number(first(state, "microprice"))
    mid = number(first(state, "mid_price", "mid"))
    spread = number(first(state, "spread", "spread_price"))
    if signal not in {"BUY", "SELL"} or None in {microprice, mid, spread} or spread < 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_inventory_microprice_signal"]
        return result
    if "max_long" in inventory and signal == "BUY" or "max_short" in inventory and signal == "SELL":
        result["view"] = "WAIT"
        result["reasons"] = ["inventory constraint rejects adding in the current direction"]
        return result
    if signal == "BUY" and microprice <= mid:
        result["view"] = "WAIT"
        result["reasons"] = ["microprice does not support the recorded buy-side quote signal"]
        return result
    if signal == "SELL" and microprice >= mid:
        result["view"] = "WAIT"
        result["reasons"] = ["microprice does not support the recorded sell-side quote signal"]
        return result
    return with_direction(result, state, signal, "inventory and microprice context support the recorded market-making side")
