"""Marcel Link's top-down multi-timeframe confirmation checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, side, values, with_direction

ALGORITHM_ID = "link_multi_timeframe_confirmation"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_weekly_trend_direction",
    "link_daily_trend_direction",
    "link_intermediate_trend_direction",
    "link_entry_timeframe_direction",
    "link_entry_stability",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    directions = [
        normalized_status(first(state, key)).upper()
        for key in (
            "link_weekly_trend_direction",
            "link_daily_trend_direction",
            "link_intermediate_trend_direction",
            "link_entry_timeframe_direction",
        )
    ]
    if candidate_side not in {"BUY", "SELL"} or any(value != candidate_side for value in directions):
        result["reasons"] = ["weekly, daily, intermediate, and entry-timeframe directions are not aligned"]
        return result
    if first(state, "link_entry_stability") is not True:
        result["reasons"] = ["the lower-timeframe entry is not observed at a stable place"]
        return result
    return with_direction(result, state, candidate_side, "all four timeframes confirm the same directional trade")
