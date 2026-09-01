"""Compression-to-expansion and volatility-breakout algorithm."""
from __future__ import annotations

from ._common import absent, base, direction, first, number, strings, values, with_direction

ALGORITHM_ID = "volatility_breakout"
SOURCES = (
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Irene Aldridge — High-Frequency Trading",
    "Anna Coulling — A Complete Guide to Volume Price Analysis",
    "Bob Volman — Forex Price Action Scalping",
)
KEYS = ("compression", "expansion", "volatility_transition", "volatility_percentile", "atr_change", "range_expansion", "breakout_state", "trend")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("volatility_transition",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if "unconfirmed" in text:
        result["view"] = "WAIT"
        result["reasons"] = ["volatility transition or breakout is explicitly unconfirmed"]
        return result
    transition = any(token in text for token in ("compression_expansion", "expansion", "range expansion", "volatility expanding"))
    if not transition:
        result["view"] = "WAIT"
        result["reasons"] = ["compression or volatility level is present without confirmed expansion"]
        return result
    signal = direction(strings(state, "breakout_state", "trend", "expansion", "volatility_transition"))
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["volatility expansion direction is not recorded"]
        return result
    percentile = number(first(state, "volatility_percentile"))
    if percentile is not None and percentile < 0:
        result["view"] = "WAIT"
        result["reasons"] = ["volatility percentile is invalid"]
        return result
    return with_direction(result, state, signal, "confirmed volatility expansion has a recorded direction")
