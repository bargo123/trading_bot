"""López de Prado symmetric CUSUM event-sampling diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import finite_series, provenance_ok

ALGORITHM_ID = "deprado_cusum_filter"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_cusum_changes",
    "deprado_cusum_expected_changes",
    "deprado_cusum_threshold",
    "deprado_cusum_data_provenance",
)


def evaluate(state):
    changes = finite_series(state, "deprado_cusum_changes")
    expected = finite_series(state, "deprado_cusum_expected_changes")
    threshold = number(first(state, "deprado_cusum_threshold"))
    found = values(state, *KEYS)
    missing = []
    if changes is None or not changes:
        missing.append("deprado_cusum_changes")
    if expected is None:
        missing.append("deprado_cusum_expected_changes")
    if threshold is None:
        missing.append("deprado_cusum_threshold")
    provenance = first(state, "deprado_cusum_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_cusum_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if len(changes) != len(expected) or threshold <= 0:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["CUSUM changes and expected changes must have equal length and a positive threshold"]
        return result

    positive = 0.0
    negative = 0.0
    events = []
    for index, (change, expectation) in enumerate(zip(changes, expected)):
        innovation = change - expectation
        positive = max(0.0, positive + innovation)
        negative = min(0.0, negative + innovation)
        if positive > threshold:
            events.append({"index": index, "direction": "UP", "cusum": positive})
            positive = 0.0
        elif negative < -threshold:
            events.append({"index": index, "direction": "DOWN", "cusum": negative})
            negative = 0.0

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "causal_event_sampling"
    result["deprado_cusum_events"] = events
    result["deprado_cusum_event_count"] = len(events)
    result["deprado_cusum_positive_state"] = positive
    result["deprado_cusum_negative_state"] = negative
    result["deprado_cusum_threshold"] = threshold
    result["deprado_cusum_assessment"] = "CHANGE_EVENTS_MEASURED"
    result["warnings"] = ["CUSUM events identify sampled changes; they do not authorize a trade"]
    return result
