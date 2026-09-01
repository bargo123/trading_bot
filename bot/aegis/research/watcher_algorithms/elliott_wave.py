"""Conservative Elliott-wave perspective from an upstream wave annotation."""
from __future__ import annotations

from ._common import base, first, strings, values, with_direction

ALGORITHM_ID = "elliott_wave"
SOURCES = (
    "A.J. Frost / Robert R. Prechter — Elliott Wave Principle",
    "Technical Analysis of the Financial Markets — John J. Murphy",
    "Mastering the Trade — John F. Carter",
)
KEYS = ("elliott_wave_state", "wave_state", "wave_count", "wave_direction", "wave_confirmation")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("wave_annotation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, *KEYS)
    if any(token in text for token in ("invalid", "failed", "unconfirmed", "unclear", "correction")):
        result["view"] = "WAIT"
        result["reasons"] = ["wave annotation is corrective, invalid, or unresolved"]
        return result
    if not any(token in text for token in ("confirmed", "complete", "trigger")):
        result["view"] = "WAIT"
        result["reasons"] = ["wave count or direction lacks an explicit confirmation"]
        return result
    if any(token in text for token in ("impulse_up", "wave_up", "bullish", "uptrend")):
        return with_direction(result, state, "BUY", "confirmed upward impulse annotation is recorded")
    if any(token in text for token in ("impulse_down", "wave_down", "bearish", "downtrend")):
        return with_direction(result, state, "SELL", "confirmed downward impulse annotation is recorded")
    result["view"] = "WAIT"
    result["reasons"] = ["wave annotation has no unambiguous direction"]
    return result
