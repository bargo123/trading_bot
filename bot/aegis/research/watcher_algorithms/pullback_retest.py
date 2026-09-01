"""Higher-timeframe pullback and level-retest algorithm."""
from __future__ import annotations
from ._common import base, direction, strings, with_direction

ALGORITHM_ID = "pullback_retest"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis", "Bob Volman — Forex Price Action Scalping", "Al Brooks — Reading Price Charts Bar by Bar", "James Dalton — Markets in Profile")
KEYS = ("pullback", "retest", "retracement", "m15_trend", "h1_trend", "structure")


def evaluate(state):
    text = strings(state, *KEYS)
    if not any(token in text for token in ("pullback", "retest", "retracement")):
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="NOT_APPLICABLE", view="NOT_APPLICABLE")
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    signal = direction(strings(state, "m15_trend", "h1_trend", "structure"))
    if "failed" in text or "unconfirmed" in text or "deep retrace" in text:
        result["view"] = "WAIT"
        result["reasons"] = ["pullback/retest appears to invalidate the prior move"]
        return result
    if any(token in text for token in ("confirmed", "support", "resistance")):
        return with_direction(result, state, signal, "pullback has a recorded level retest in higher-timeframe context")
    result["view"] = "WAIT"
    result["reasons"] = ["pullback is visible but retest confirmation is absent"]
    return result
