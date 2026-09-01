"""Higher-timeframe directional alignment algorithm."""
from __future__ import annotations
from ._common import absent, base, direction, values, with_direction

ALGORITHM_ID = "higher_timeframe_alignment"
SOURCES = ("Adam Grimes — The Art and Science of Technical Analysis", "Al Brooks — Reading Price Charts Bar by Bar", "Alexander Elder — The New Trading for a Living", "James Dalton — Markets in Profile")
KEYS = ("m15_trend", "h1_trend", "m15_context", "h1_context", "higher_timeframe", "regime")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("m15_or_h1_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    directions = [direction(value) for _, value in found]
    directions = [value for value in directions if value]
    if directions and len(set(directions)) == 1:
        return with_direction(result, state, directions[0], "higher-timeframe directions align")
    result["view"] = "WAIT"
    result["reasons"] = ["higher-timeframe context is conflicting or non-directional"]
    return result
