"""Read-only trend-continuation perspective from the reviewed price-action texts."""
from __future__ import annotations

from ._common import base, first, normalized_status, side, values, with_direction

ALGORITHM_ID = "trend_continuation"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Bob Volman — Forex Price Action Scalping",
    "Robert Carver — Systematic Trading",
)
KEYS = ("trend", "m15_trend", "h1_trend", "structure", "pullback", "retest", "follow_through", "breakout_state")


def _trend_direction(state):
    for key in ("trend", "m15_trend", "h1_trend"):
        value = normalized_status(first(state, key))
        if value in {"up", "bullish", "uptrend"}:
            return "BUY"
        if value in {"down", "bearish", "downtrend"}:
            return "SELL"
    return None


def _continuation_observed(state):
    for key in ("pullback", "retest", "follow_through", "breakout_state"):
        value = normalized_status(first(state, key))
        if not value or any(token in value for token in ("failed", "not observed", "not confirmed", "unconfirmed")):
            continue
        if any(token in value for token in ("reclaimed", "confirmed", "present", "continuation", "breakout")):
            return key
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("trend_context", "continuation_trigger"))
    trend = _trend_direction(state)
    trigger = _continuation_observed(state)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if trend is None:
        result["view"] = "WAIT"
        result["reasons"] = ["trend direction is unresolved"]
        return result
    if trigger is None:
        result["view"] = "WAIT"
        result["reasons"] = ["no observed pullback, retest, follow-through, or confirmed break for continuation"]
        return result
    result = with_direction(result, state, trend, f"{trend} trend has an observed {trigger} continuation trigger")
    result["continuation_trigger"] = trigger
    return result

