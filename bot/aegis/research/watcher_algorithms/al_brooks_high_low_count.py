"""Al Brooks High/Low 1-4 pullback-count perspective.

Brooks describes the count as repeated attempts to end a pullback. A count
alone is insufficient: the copied state must also show prior strength or a
minor trendline break and a confirmed context. This is a read-only shadow
perspective.
"""
from __future__ import annotations

from ._common import absent, base, direction, explicitly_confirmed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "al_brooks_high_low_count"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "bar_count_direction",
    "bar_count",
    "bar_count_context",
    "bar_count_trendline_break",
    "bar_count_confirmation",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_high_low_count",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    count = number(first(state, "bar_count"))
    signal = direction(first(state, "bar_count_direction"))
    context = normalized_status(first(state, "bar_count_context"))
    if count is None or not count.is_integer() or count < 1 or count > 4:
        result["view"] = "WAIT"
        result["reasons"] = ["High/Low bar count must be an integer from 1 through 4"]
        return result
    if signal is None or not explicitly_confirmed(first(state, "bar_count_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["bar count lacks an explicit directional confirmation"]
        return result
    if first(state, "bar_count_trendline_break") is not True:
        result["view"] = "WAIT"
        result["reasons"] = ["bar count is not supported by the prior strength/trendline break described by Brooks"]
        return result
    if not any(token in context for token in ("bull", "bear", "pullback", "trend", "correction")):
        result["view"] = "WAIT"
        result["reasons"] = ["bar count has no explicit pullback or trend context"]
        return result
    result["bar_count_setup"] = f"{signal}_{int(count)}"
    result["bar_count"] = int(count)
    return with_direction(result, state, signal, "confirmed High/Low pullback count follows a prior strength break")
