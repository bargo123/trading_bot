"""Liquidity sweep, stop-run, and reclaim algorithm."""
from __future__ import annotations

from ._common import absent, base, strings, values, with_direction

ALGORITHM_ID = "liquidity_sweep"
SOURCES = (
    "Jean-Philippe Bouchaud — Trades, Quotes and Prices",
    "Joel Hasbrouck — Empirical Market Microstructure",
    "Irene Aldridge — High-Frequency Trading",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = ("liquidity_sweep", "stop_run", "equal_highs", "equal_lows", "sweep_state", "reclaim", "wick_rejection", "liquidity")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("liquidity_sweep_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("sell_side_sweep_reclaimed", "sell-side sweep reclaimed", "low swept reclaimed", "bullish reclaim")):
        return with_direction(result, state, "BUY", "sell-side liquidity was swept and reclaimed")
    if any(token in text for token in ("buy_side_sweep_rejected", "buy-side sweep rejected", "high swept rejected", "bearish rejection")):
        return with_direction(result, state, "SELL", "buy-side liquidity was swept and rejected")
    if "sweep" in text:
        result["view"] = "WAIT"
        result["reasons"] = ["liquidity sweep is recorded without a confirmed reclaim or rejection"]
        return result
    result["view"] = "WAIT"
    result["reasons"] = ["liquidity references are present but no sweep event is confirmed"]
    return result
