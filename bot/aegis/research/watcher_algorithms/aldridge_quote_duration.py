"""Aldridge inter-quote duration/activity diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "aldridge_quote_duration"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_interquote_duration_ms",
    "aldridge_duration_baseline_ms",
    "aldridge_duration_context",
    "aldridge_duration_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    duration = number(first(state, "aldridge_interquote_duration_ms"))
    baseline = number(first(state, "aldridge_duration_baseline_ms"))
    context = normalized_status(first(state, "aldridge_duration_context"))
    missing = [
        key for key, value in (
            ("aldridge_interquote_duration_ms", duration),
            ("aldridge_duration_baseline_ms", baseline),
            ("aldridge_duration_context", context or None),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "aldridge_duration_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("aldridge_duration_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if duration <= 0 or baseline <= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["inter-quote duration and baseline must be positive"]
        return result
    ratio = duration / baseline
    result["aldridge_duration_ratio"] = ratio
    result["aldridge_duration_context"] = context
    if ratio < 1.0:
        result["aldridge_duration_assessment"] = "SHORT_DURATION_ACTIVITY"
        result["reasons"] = ["inter-quote duration is shorter than the observed baseline"]
    elif ratio > 1.0:
        result["aldridge_duration_assessment"] = "LONG_DURATION_INACTIVITY"
        result["reasons"] = ["inter-quote duration is longer than the observed baseline"]
    else:
        result["aldridge_duration_assessment"] = "BASELINE_DURATION"
        result["reasons"] = ["inter-quote duration matches the observed baseline"]
    result["warnings"] = ["duration is activity context and does not identify BUY or SELL by itself"]
    return result

