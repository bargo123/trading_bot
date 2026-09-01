"""Marcel Link's double-top/double-bottom reversal checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, side, values, with_direction

ALGORITHM_ID = "link_double_top_bottom_reversal"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_reversal_pattern",
    "link_previous_extreme_failed",
    "link_trendline_break_confirmed",
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
    if first(state, "link_previous_extreme_failed") is not True or first(state, "link_trendline_break_confirmed") is not True:
        result["reasons"] = ["the repeated extreme has not failed and broken its trendline"]
        return result
    pattern = normalized_status(first(state, "link_reversal_pattern"))
    signal = "BUY" if pattern == "double bottom" else "SELL" if pattern == "double top" else None
    if signal is None:
        result["reasons"] = ["the observed reversal pattern is not a double top or double bottom"]
        return result
    return with_direction(result, state, signal, "repeated extreme failed and the reversal trendline broke")
