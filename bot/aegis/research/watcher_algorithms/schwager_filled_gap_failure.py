"""Jack Schwager's rigid close-confirmed filled-gap failure study."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "schwager_filled_gap_failure"
SOURCES = ("Jack Schwager — Getting Started in Technical Analysis",)
KEYS = (
    "schwager_gap_direction",
    "schwager_gap_filled_by_close",
    "schwager_gap_width_class",
    "schwager_gap_breakaway",
    "schwager_consecutive_gaps_filled",
    "schwager_filled_gap_invalidated",
    "schwager_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upside", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downside", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "schwager_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("schwager_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    gap = _direction(first(state, "schwager_gap_direction"))
    consecutive = number(first(state, "schwager_consecutive_gaps_filled"))
    if gap is None or consecutive is None or consecutive < 1:
        result["view"] = "WAIT"
        result["schwager_gap_assessment"] = "GAP_INPUT_INVALID"
        result["reasons"] = ["gap direction and at least one filled gap are required"]
        return result
    if not _truthy(first(state, "schwager_gap_filled_by_close")):
        result["view"] = "WAIT"
        result["schwager_gap_assessment"] = "CLOSE_FILL_REQUIRED"
        result["reasons"] = ["the source prefers a close through the prior close, not an intraday touch"]
        return result
    if _truthy(first(state, "schwager_filled_gap_invalidated")):
        result["view"] = "WAIT"
        result["schwager_gap_assessment"] = "GAP_FAILURE_INVALIDATED"
        result["reasons"] = ["price closed beyond the gap boundary that keeps the failed signal in force"]
        return result
    signal = "SELL" if gap == "BUY" else "BUY"
    result["schwager_gap_assessment"] = "FILLED_GAP_FAILURE"
    result["schwager_gap_enhanced"] = (
        normalized_status(first(state, "schwager_gap_width_class")) == "wide"
        or _truthy(first(state, "schwager_gap_breakaway"))
        or consecutive > 1
    )
    return with_direction(result, state, signal, "the rigid close-based gap fill treats the original gap as a failed signal")
