"""Read-only trend-pullback perspective from price-action research."""
from __future__ import annotations

from ._common import base, first, normalized_status, values, with_direction

ALGORITHM_ID = "trend_pullback"
SOURCES = (
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = ("trend", "m5_trend", "m15_trend", "h1_trend", "pullback", "retracement", "retest")


def _direction(state):
    for key in ("trend", "m5_trend", "m15_trend", "h1_trend"):
        value = normalized_status(first(state, key))
        if value in {"up", "bullish", "uptrend"}:
            return "BUY"
        if value in {"down", "bearish", "downtrend"}:
            return "SELL"
    return None


def _confirmed_pullback(state):
    for key in ("pullback", "retracement", "retest"):
        value = normalized_status(first(state, key))
        if not value or any(token in value for token in ("failed", "not observed", "not confirmed", "unconfirmed")):
            continue
        if any(token in value for token in ("reclaimed", "confirmed", "pullback", "retracement")):
            return key
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("trend_context", "pullback_context"))
    direction = _direction(state)
    pullback = _confirmed_pullback(state)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if direction is None or pullback is None:
        result["view"] = "WAIT"
        result["reasons"] = ["trend and confirmed pullback/retest are both required"]
        return result
    result = with_direction(result, state, direction, f"{direction} trend pullback has a {pullback} response")
    result["pullback_trigger"] = pullback
    return result

