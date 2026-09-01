"""Aldridge/Vega market-order aggressiveness perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "aldridge_trade_aggressiveness"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_aggressive_buy_fraction",
    "aldridge_aggressive_sell_fraction",
    "aldridge_aggressiveness_state",
    "aldridge_trade_observation_n",
    "aldridge_trade_aggressiveness_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable", "tick", "quote")
    ) and any(token in provenance for token in ("market limit", "order type", "classified market"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "aldridge_trade_aggressiveness_provenance")):
        missing.append("aldridge_trade_aggressiveness_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    buy = number(first(state, "aldridge_aggressive_buy_fraction"))
    sell = number(first(state, "aldridge_aggressive_sell_fraction"))
    observations = number(first(state, "aldridge_trade_observation_n"))
    state_label = normalized_status(first(state, "aldridge_aggressiveness_state"))
    if None in {buy, sell, observations} or observations <= 0 or any(value < 0 or value > 1 for value in (buy, sell)):
        result["view"] = "WAIT"
        result["reasons"] = ["aggressive order shares must be finite fractions with observations"]
        return result
    if state_label not in {"high", "elevated", "high aggressiveness"}:
        result["view"] = "WAIT"
        result["reasons"] = ["low or unresolved market-order aggressiveness is not a directional signal"]
        return result
    if buy > sell:
        result["aldridge_trade_aggressiveness_assessment"] = "AGGRESSIVE_BUY_FLOW"
        return with_direction(result, state, "BUY", "classified market-order share is more aggressive on the buy side")
    if sell > buy:
        result["aldridge_trade_aggressiveness_assessment"] = "AGGRESSIVE_SELL_FLOW"
        return with_direction(result, state, "SELL", "classified market-order share is more aggressive on the sell side")
    result["view"] = "WAIT"
    result["reasons"] = ["buy and sell aggressive order shares are equal"]
    return result
