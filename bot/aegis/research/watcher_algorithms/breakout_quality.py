"""Breakout, retest, and failed-break algorithm."""
from __future__ import annotations
from ._common import base, direction, strings, with_direction

ALGORITHM_ID = "breakout_quality"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis", "Bob Volman — Forex Price Action Scalping", "Al Brooks — Reading Price Charts Bar by Bar", "Alexander Elder — The New Trading for a Living")
KEYS = ("structure", "breakout", "breakout_state", "retest", "impulse", "compression", "volume", "follow_through")


def evaluate(state):
    text = strings(state, *KEYS)
    if not any(token in text for token in ("breakout", "range break", "squeeze", "compression")):
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="NOT_APPLICABLE", view="NOT_APPLICABLE")
    result = base(ALGORITHM_ID, state, SOURCES, KEYS)
    if any(token in text for token in ("failed", "false", "unconfirmed", "tease", "deep retrace", "no follow")):
        result["view"] = "WAIT"
        result["reasons"] = ["breakout failure or weak follow-through is present"]
        result["warnings"] = ["a premature break is not treated as confirmed continuation"]
        return result
    signal = direction(strings(state, "breakout", "structure", "trend"))
    if any(token in text for token in ("retest", "confirmed", "follow", "volume")):
        return with_direction(result, state, signal, "breakout has a recorded retest, confirmation, or follow-through input")
    result["view"] = "WAIT"
    result["reasons"] = ["breakout is present but confirmation is not recorded"]
    return result
