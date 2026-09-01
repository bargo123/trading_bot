"""Aldridge bid/ask-bounce data-quality diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "aldridge_bid_ask_bounce_filter"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_bid_ask_bounce_detected",
    "aldridge_midquote_filter_applied",
    "aldridge_bid_ask_bounce_autocorrelation",
    "aldridge_bid_ask_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "detected", "applied", "filtered"}:
        return True
    if label in {"false", "no", "not detected", "not applied", "unfiltered"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    detected = _boolean(first(state, "aldridge_bid_ask_bounce_detected"))
    filtered = _boolean(first(state, "aldridge_midquote_filter_applied"))
    autocorrelation = number(first(state, "aldridge_bid_ask_bounce_autocorrelation"))
    missing = [
        key for key, value in (
            ("aldridge_bid_ask_bounce_detected", detected),
            ("aldridge_midquote_filter_applied", filtered),
            ("aldridge_bid_ask_bounce_autocorrelation", autocorrelation),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "aldridge_bid_ask_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("aldridge_bid_ask_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if not -1.0 <= autocorrelation <= 1.0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["bounce autocorrelation must be within [-1, 1]"]
        return result
    if detected and not filtered:
        assessment = "BOUNCE_CONTAMINATION"
        reason = "bid/ask bounce is observed and no midquote/noise filter is recorded"
    elif detected:
        assessment = "FILTERED_BOUNCE"
        reason = "observed bid/ask bounce is explicitly filtered before return analysis"
    else:
        assessment = "NO_BOUNCE_DETECTED"
        reason = "the copied quote sequence does not record bid/ask-bounce contamination"
    result["aldridge_bounce_assessment"] = assessment
    result["aldridge_bid_ask_bounce_autocorrelation"] = autocorrelation
    result["reasons"] = [reason]
    return result

