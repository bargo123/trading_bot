"""Chan's signed transaction-flow momentum perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "chan_order_flow_momentum"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_order_flow_value",
    "chan_order_flow_min_abs",
    "chan_order_flow_lookback",
    "chan_order_flow_source",
    "chan_order_flow_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = first(state, "chan_order_flow_data_provenance")
    source = normalized_status(first(state, "chan_order_flow_source"))
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped")):
        missing.append("chan_order_flow_data_provenance")
    if not any(token in source for token in ("signed transaction", "real transaction", "trade flow")):
        missing.append("chan_order_flow_source")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    flow = number(first(state, "chan_order_flow_value"))
    minimum = number(first(state, "chan_order_flow_min_abs"))
    lookback = number(first(state, "chan_order_flow_lookback"))
    if flow is None or minimum is None or lookback is None or minimum <= 0 or lookback <= 0:
        result["chan_order_flow_assessment"] = "INVALID_FLOW_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["signed flow, threshold, and lookback must be finite positive observations"]
        return result
    if abs(flow) < minimum or flow == 0:
        result["chan_order_flow_assessment"] = "INSUFFICIENT_FLOW"
        result["view"] = "WAIT"
        result["reasons"] = ["signed transaction flow did not reach the measured threshold"]
        return result
    result["chan_order_flow_assessment"] = "POSITIVE_FLOW" if flow > 0 else "NEGATIVE_FLOW"
    return with_direction(result, state, "BUY" if flow > 0 else "SELL", "signed transaction flow supplies the short-horizon direction")
