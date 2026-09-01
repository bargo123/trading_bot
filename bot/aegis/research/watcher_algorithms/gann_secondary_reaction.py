"""W. D. Gann's secondary-rally/lower-top and secondary-decline rule."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "gann_secondary_reaction"
SOURCES = ("W. D. Gann — How to Make Profits in Commodities",)
SOURCE_PAGES = "pp. 30-33"
KEYS = (
    "gann_primary_trend",
    "gann_secondary_pattern",
    "gann_secondary_after_primary_move",
    "gann_secondary_confirmed",
    "gann_secondary_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "gann_secondary_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("gann_secondary_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    primary = normalized_status(first(state, "gann_primary_trend"))
    if primary not in {"bullish", "bearish", "up", "down", "advancing", "declining"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the primary trend must be explicit before a secondary reaction is interpreted"]
        return result
    if not volman_truth(first(state, "gann_secondary_after_primary_move")):
        result["view"] = "WAIT"
        result["reasons"] = ["the reaction is not observed after a primary move"]
        return result
    if not volman_truth(first(state, "gann_secondary_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the secondary reaction is not confirmed"]
        return result

    pattern = normalized_status(first(state, "gann_secondary_pattern"))
    if pattern in {"lower top", "lower high"}:
        signal = "SELL"
        assessment = "SECONDARY_RALLY_LOWER_TOP"
    elif pattern in {"higher bottom", "higher low"}:
        signal = "BUY"
        assessment = "SECONDARY_DECLINE_HIGHER_BOTTOM"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["only a confirmed lower top or higher bottom is a source-defined secondary reaction"]
        return result
    result["gann_secondary_assessment"] = assessment
    return with_direction(result, state, signal, "the confirmed secondary reaction formed a directional lower top or higher bottom")
