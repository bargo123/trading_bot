"""Price-in-Time abnormal-day exclusion perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth

ALGORITHM_ID = "price_in_time_anomaly_filter"
SOURCES = ("The Price in Time — Forex Strategy",)
KEYS = (
    "pit_anomalous_day",
    "pit_asian_width_pips",
    "pit_asian_range_limit_pips",
    "pit_anomaly_data_provenance",
)


def _risk_state(value) -> bool:
    label = normalized_status(value)
    return any(token in label for token in ("important", "high risk", "scheduled risk", "holiday", "closed", "catastrophe", "political"))


def _clear_state(value) -> bool:
    label = normalized_status(value)
    return label in {"clear", "none", "normal", "open", "no", "false"}


def evaluate(state):
    found = values(state, *KEYS)
    anomaly = first(state, "pit_anomalous_day")
    asian_width = number(first(state, "pit_asian_width_pips"))
    limit = number(first(state, "pit_asian_range_limit_pips"))
    missing = []
    if anomaly is None:
        missing.append("pit_anomalous_day")
    if asian_width is None:
        missing.append("pit_asian_width_pips")
    if limit is None:
        missing.append("pit_asian_range_limit_pips")
    if not explicitly_observed(first(state, "pit_anomaly_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("pit_anomaly_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if asian_width < 0 or limit <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["Asian quote range and its source limit must be non-negative and positive"]
        return result
    anomaly_label = normalized_status(anomaly)
    quote_anomaly = volman_truth(anomaly) or "anomalous" in anomaly_label or asian_width > limit
    macro = first(state, "pit_macro_event_state")
    holiday = first(state, "pit_holiday_state")
    if quote_anomaly or _risk_state(macro) or _risk_state(holiday):
        result["pit_anomaly_assessment"] = "EXCLUDE_ABNORMAL_DAY"
        result["pit_session_action"] = "NO_TRADE"
        result["reasons"] = ["the observed Asian range or explicit event/holiday state violates the source day-selection rule"]
        return result
    result["pit_anomaly_assessment"] = "NORMAL_DAY_QUOTE_PROXY"
    result["pit_session_action"] = "ALLOW_SOURCE_DAY"
    result["reasons"] = ["the observed Asian range is within its configured source limit"]
    if macro is None or holiday is None or not (_clear_state(macro) and _clear_state(holiday)):
        result["warnings"] = ["macro-calendar and holiday exclusion were not fully observed; quote-range clearance is only a proxy"]
    return result
