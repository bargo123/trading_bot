"""Al Brooks' micro-measuring-gap strength perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "brooks_micro_measuring_gap"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "side",
    "brooks_gap_trend_direction",
    "brooks_gap_trend_bar_strength",
    "brooks_gap_before_high",
    "brooks_gap_before_low",
    "brooks_gap_after_high",
    "brooks_gap_after_low",
    "brooks_gap_data_provenance",
)


def _brooks_provenance_ok(value) -> bool:
    # The feature adapter's completed quote bars are an observed, explicitly
    # labelled proxy for chart bars.  Accept that one exact provenance label;
    # synthetic, fixture, and unverified labels remain fail-closed.
    return normalized_status(value) == "completed quote bar proxy" or explicitly_observed(
        value,
        accepted=("observed", "measured", "historical", "timestamped"),
    )


def _strong(value) -> bool:
    return value is True or normalized_status(value) in {"strong", "strong trend", "confirmed strong"}


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _brooks_provenance_ok(first(state, "brooks_gap_data_provenance")):
        missing.append("brooks_gap_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["brooks_gap_signal_role"] = "STRENGTH_CONTEXT"
    side = normalized_status(first(state, "side")).upper()
    direction = normalized_status(first(state, "brooks_gap_trend_direction"))
    before_high = number(first(state, "brooks_gap_before_high"))
    before_low = number(first(state, "brooks_gap_before_low"))
    after_high = number(first(state, "brooks_gap_after_high"))
    after_low = number(first(state, "brooks_gap_after_low"))
    result["view"] = "WAIT"
    if side not in {"BUY", "SELL"} or direction not in {"up", "down"}:
        result["reasons"] = ["the gap direction and candidate side must be explicit"]
        return result
    if any(value is None for value in (before_high, before_low, after_high, after_low)) or before_high <= before_low or after_high <= after_low:
        result["reasons"] = ["the before/after bars must have finite, ordered highs and lows"]
        return result
    if not _strong(first(state, "brooks_gap_trend_bar_strength")):
        result["reasons"] = ["the source micro-measuring gap follows a strong trend bar"]
        return result
    nonoverlap = after_low > before_high if direction == "up" else after_high < before_low
    if not nonoverlap:
        result["reasons"] = ["the bars surrounding the trend bar overlap, so no micro-measuring gap is observed"]
        return result
    result["brooks_gap_assessment"] = "BULL_MICRO_MEASURING_GAP" if direction == "up" else "BEAR_MICRO_MEASURING_GAP"
    if (direction == "up" and side == "BUY") or (direction == "down" and side == "SELL"):
        return with_direction(result, state, side, "the strong trend bar is bracketed by a same-direction non-overlap")
    result["reasons"] = ["the observed micro-measuring gap conflicts with the candidate side"]
    return result
