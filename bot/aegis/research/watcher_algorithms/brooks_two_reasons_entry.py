"""Al Brooks' two-reasons entry and steep-countertrend exception perspective."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, normalized_status, side, values, with_direction

ALGORITHM_ID = "brooks_two_reasons_entry"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "side",
    "brooks_entry_reasons",
    "brooks_strong_trend",
    "brooks_second_entry",
    "brooks_trendline_overshoot_reversal",
    "brooks_countertrend",
    "brooks_two_reasons_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "confirmed", "present", "observed"}:
        return True
    if label in {"false", "no", "unconfirmed", "absent", "missing"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    candidate_side = side(state)
    if not candidate_side:
        missing.append("side")
    reasons = first(state, "brooks_entry_reasons")
    if isinstance(reasons, (str, bytes, bytearray)) or not isinstance(reasons, Sequence):
        missing.append("brooks_entry_reasons")
    if not explicitly_observed(
        first(state, "brooks_two_reasons_data_provenance"),
        accepted=("observed", "measured", "historical", "timestamped"),
    ):
        missing.append("brooks_two_reasons_data_provenance")
    booleans = {
        key: _boolean(first(state, key))
        for key in (
            "brooks_strong_trend",
            "brooks_second_entry",
            "brooks_trendline_overshoot_reversal",
            "brooks_countertrend",
        )
    }
    missing.extend(key for key, value in booleans.items() if value is None)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    normalized_reasons = []
    for value in reasons:
        label = normalized_status(value)
        if label and label not in normalized_reasons:
            normalized_reasons.append(label)
    result["brooks_entry_reasons"] = normalized_reasons
    result["brooks_entry_reason_count"] = len(normalized_reasons)
    result.update(booleans)
    result["directional_claim"] = True

    if booleans["brooks_countertrend"] and booleans["brooks_strong_trend"] and not booleans["brooks_trendline_overshoot_reversal"]:
        result["brooks_two_reasons_assessment"] = "COUNTERTREND_AGAINST_STEEP_TREND"
        result["reasons"] = ["the source rejects a steep countertrend entry without a prior trendline break or overshoot reversal"]
        return result

    if len(normalized_reasons) >= 2:
        result["brooks_two_reasons_assessment"] = "TWO_REASONS_CONFIRMED"
        return with_direction(result, state, candidate_side, "at least two distinct observed entry reasons are present")

    exception = None
    if booleans["brooks_second_entry"]:
        exception = "SECOND_ENTRY_SINGLE_REASON_EXCEPTION"
    elif booleans["brooks_trendline_overshoot_reversal"]:
        exception = "OVERSHOOT_REVERSAL_SINGLE_REASON_EXCEPTION"
    elif booleans["brooks_strong_trend"] and not booleans["brooks_countertrend"]:
        exception = "STRONG_TREND_SINGLE_REASON_EXCEPTION"
    if exception and normalized_reasons:
        result["brooks_two_reasons_assessment"] = exception
        return with_direction(result, state, candidate_side, "a source-documented one-reason exception is present")

    result["brooks_two_reasons_assessment"] = "NEEDS_TWO_REASONS"
    result["view"] = "WAIT"
    result["reasons"] = ["the source requires two distinct entry reasons outside its documented exceptions"]
    return result
