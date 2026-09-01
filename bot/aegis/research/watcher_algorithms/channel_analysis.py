"""Price-channel continuation, rejection, and breakout algorithm."""
from __future__ import annotations

from ._common import absent, base, direction, strings, values, with_direction

ALGORITHM_ID = "channel_analysis"
SOURCES = (
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
    "Adam Grimes — The Art and Science of Technical Analysis",
    "Al Brooks — Reading Price Charts Bar by Bar",
    "John F. Carter — Mastering the Trade",
)
KEYS = ("channel_state", "channel_direction", "channel_upper", "channel_lower", "channel_position", "channel_breakout", "trend_channel", "price_position")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("channel_state",))
    text = strings(state, *KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if any(token in text for token in ("failed", "false", "invalid")):
        result["view"] = "WAIT"
        result["reasons"] = ["channel break or rejection is recorded as failed"]
        return result
    signal = direction(text)
    if signal is None and any(token in text for token in ("upper_breakout", "breakout_up", "ascending")):
        signal = "BUY"
    elif signal is None and any(token in text for token in ("lower_breakdown", "breakdown_down", "descending")):
        signal = "SELL"
    if signal:
        return with_direction(result, state, signal, "channel direction or confirmed boundary break is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["channel boundaries are available but direction or confirmation is unresolved"]
    return result
