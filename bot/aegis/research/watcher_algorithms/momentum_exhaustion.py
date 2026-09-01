"""Momentum persistence, climax, and exhaustion algorithm."""
from __future__ import annotations
from ._common import absent, base, direction, first, number, strings, values, with_direction

ALGORITHM_ID = "momentum_exhaustion"
SOURCES = ("Al Brooks — Reading Price Charts Bar by Bar", "Adam Grimes — The Art and Science of Technical Analysis", "Anna Coulling — A Complete Guide to Volume Price Analysis", "Ernest Chan — Machine Trading")
KEYS = ("momentum", "momentum_context", "short_returns", "return_1", "return_3", "divergence", "exhaustion", "climax", "follow_through")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("momentum_or_returns",))
    text = " ".join(str(value).lower() for _, value in found)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    divergence_warning = any(token in text for token in ("bullish_divergence", "bearish_divergence", "positive_divergence", "negative_divergence"))
    exhaustion_warning = any(token in text for token in ("exhaust", "climax", "waning"))
    if exhaustion_warning or divergence_warning:
        result["view"] = "WAIT"
        result["reasons"] = ["momentum exhaustion or divergence warning is present"]
        result["warnings"] = ["do not chase a move after its measured impulse weakens"]
        return result
    signal = direction(text)
    numeric = [number(value) for _, value in found]
    numeric = [value for value in numeric if value is not None]
    if signal is None and numeric:
        signal = "BUY" if sum(numeric) > 0 else "SELL" if sum(numeric) < 0 else None
    return with_direction(result, state, signal, "recent directional persistence is recorded")
