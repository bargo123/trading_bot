"""Pole's event-history pair-selection diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "pole_event_pair_selection"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_event_similarity",
    "pole_interevent_return_correlation",
    "pole_min_event_similarity",
    "pole_max_interevent_return_correlation",
    "pole_pair_selection_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_pair_selection_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("pole_pair_selection_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in values(state, *KEYS)])
    similarity = number(first(state, "pole_event_similarity"))
    correlation = number(first(state, "pole_interevent_return_correlation"))
    minimum_similarity = number(first(state, "pole_min_event_similarity"))
    maximum_correlation = number(first(state, "pole_max_interevent_return_correlation"))
    if (
        similarity is None
        or correlation is None
        or minimum_similarity is None
        or maximum_correlation is None
        or not 0.0 <= similarity <= 1.0
        or not 0.0 <= minimum_similarity <= 1.0
        or not -1.0 <= correlation <= 1.0
        or not -1.0 <= maximum_correlation <= 1.0
    ):
        result["pole_pair_selection_action"] = "INVALID_EVENT_INPUT"
        result["reasons"] = ["event similarity must be in [0,1] and correlations in [-1,1]"]
        return result

    result.update(
        {
            "pole_pair_risk_event_similarity": similarity,
            "pole_pair_interevent_return_correlation": correlation,
            "pole_pair_selection_min_similarity": minimum_similarity,
            "pole_pair_selection_max_correlation": maximum_correlation,
        }
    )
    failures = []
    if similarity < minimum_similarity:
        failures.append("event histories are not sufficiently similar for the source risk screen")
    if correlation > maximum_correlation:
        failures.append("interevent returns are not sufficiently dispersed for the source profit screen")
    if failures:
        result["pole_pair_selection_action"] = "REJECT_PAIR"
        result["reasons"] = failures
    else:
        result["pole_pair_selection_action"] = "SELECT_PAIR"
        result["reasons"] = ["event-history similarity and interevent return dispersion pass the observed pair screen"]
    return result

