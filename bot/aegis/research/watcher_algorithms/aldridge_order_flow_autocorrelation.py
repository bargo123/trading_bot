"""Aldridge high-frequency order-flow persistence perspective.

The source distinguishes positive short-horizon order-flow autocorrelation from
negative lower-frequency correlation.  A direction is emitted only when the
copied observation is explicitly classified from buyer/seller trades; a tick
or quote proxy is not silently promoted to order-flow truth.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "aldridge_order_flow_autocorrelation"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_order_flow_imbalance",
    "aldridge_order_flow_autocorrelation",
    "aldridge_order_flow_frequency",
    "aldridge_order_flow_observation_n",
    "aldridge_order_flow_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable", "tick proxy", "quote proxy")
    ) and any(token in provenance for token in ("buyer seller", "classified trade", "market buy", "market sell", "trade classification"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "aldridge_order_flow_data_provenance")):
        missing.append("aldridge_order_flow_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    imbalance = number(first(state, "aldridge_order_flow_imbalance"))
    autocorrelation = number(first(state, "aldridge_order_flow_autocorrelation"))
    observations = number(first(state, "aldridge_order_flow_observation_n"))
    frequency = normalized_status(first(state, "aldridge_order_flow_frequency"))
    if imbalance is None or autocorrelation is None or observations is None or observations <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["order-flow persistence requires finite imbalance, correlation, and observations"]
        return result
    if not -1.0 <= autocorrelation <= 1.0:
        result["view"] = "WAIT"
        result["reasons"] = ["order-flow autocorrelation is outside the [-1, 1] range"]
        return result
    if frequency not in {"high frequency", "hf", "high frequency data"} or autocorrelation <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["only positive high-frequency order-flow persistence supports this perspective"]
        return result
    if imbalance > 0:
        result["aldridge_order_flow_assessment"] = "PERSISTENT_BUY_FLOW"
        return with_direction(result, state, "BUY", "positive high-frequency buyer-initiated order-flow imbalance persisted")
    if imbalance < 0:
        result["aldridge_order_flow_assessment"] = "PERSISTENT_SELL_FLOW"
        return with_direction(result, state, "SELL", "negative high-frequency seller-initiated order-flow imbalance persisted")
    result["view"] = "WAIT"
    result["reasons"] = ["buyer- and seller-initiated order flow is balanced"]
    return result
