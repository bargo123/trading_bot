"""Spread, quote-state, persistence, and imbalance algorithm."""
from __future__ import annotations
from ._common import base, first, number, side, values, with_direction

ALGORITHM_ID = "microstructure"
SOURCES = ("Jean-Philippe Bouchaud — Trades, Quotes and Prices", "Joel Hasbrouck — Empirical Market Microstructure", "Irene Aldridge — High-Frequency Trading", "Frank de Jong — The Microstructure of Financial Markets")
KEYS = ("spread", "spread_pips", "quote_age_s", "quote_fresh", "tick_persistence", "order_flow", "imbalance", "bid_ask_imbalance", "queue_imbalance")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("quote_and_microstructure",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    age = number(first(state, "quote_age_s"))
    if first(state, "quote_fresh") is False or (age is not None and age > 5):
        result["view"] = "WAIT"
        result["reasons"] = ["quote freshness or advancement is insufficient"]
        return result
    imbalance = number(first(state, "imbalance", "bid_ask_imbalance", "queue_imbalance"))
    if imbalance is not None and imbalance != 0:
        return with_direction(result, state, "BUY" if imbalance > 0 else "SELL", "signed quote or queue imbalance is recorded")
    persistence = number(first(state, "tick_persistence"))
    if persistence is not None and persistence != 0:
        return with_direction(result, state, "BUY" if persistence > 0 else "SELL", "signed recent order-flow persistence is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["quote exists but directional microstructure evidence is unresolved"]
    return result
