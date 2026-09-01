"""Cartea--Jaimungal state-conditioned activity and revision diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "cartea_state_intensity"
SOURCES = ("Modelling Asset Prices for Algorithmic and High-Frequency Trading",)
KEYS = (
    "cartea_state_duration_s",
    "cartea_state_revision_volatility",
    "cartea_state_zero_revision_probability",
    "cartea_state_persistence",
    "cartea_median_duration_s",
    "cartea_median_revision_volatility",
    "cartea_median_zero_revision_probability",
    "cartea_median_persistence",
    "cartea_state_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "cartea_state_data_provenance"),
        accepted=("observed", "timestamped", "tick"),
    ):
        missing.append("cartea_state_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    current = {
        "duration": number(first(state, "cartea_state_duration_s")),
        "revision_volatility": number(first(state, "cartea_state_revision_volatility")),
        "zero_revision": number(first(state, "cartea_state_zero_revision_probability")),
        "persistence": number(first(state, "cartea_state_persistence")),
    }
    medians = {
        "duration": number(first(state, "cartea_median_duration_s")),
        "revision_volatility": number(first(state, "cartea_median_revision_volatility")),
        "zero_revision": number(first(state, "cartea_median_zero_revision_probability")),
        "persistence": number(first(state, "cartea_median_persistence")),
    }
    if (
        any(value is None or value < 0 for value in current.values())
        or any(value is None or value <= 0 for value in medians.values())
        or current["zero_revision"] > 1
        or current["persistence"] > 1
        or medians["zero_revision"] > 1
        or medians["persistence"] > 1
    ):
        result["cartea_state_assessment"] = "INVALID_STATE_INPUT"
        result["reasons"] = ["state statistics and cross-state medians must be finite and within valid ranges"]
        return result

    def relative(value, median, *, lower_is_favorable=True):
        if value == median:
            return "TYPICAL"
        favorable = value < median if lower_is_favorable else value > median
        return "FAVORABLE" if favorable else "UNFAVORABLE"

    activity = relative(current["duration"], medians["duration"], lower_is_favorable=True)
    revision = relative(current["revision_volatility"], medians["revision_volatility"], lower_is_favorable=True)
    zero_revision = relative(current["zero_revision"], medians["zero_revision"], lower_is_favorable=False)
    persistence = relative(current["persistence"], medians["persistence"], lower_is_favorable=False)
    result["cartea_activity_class"] = "FAST" if activity == "FAVORABLE" else "SLOW" if activity == "UNFAVORABLE" else "TYPICAL"
    result["cartea_revision_class"] = "LOW" if revision == "FAVORABLE" else "HIGH" if revision == "UNFAVORABLE" else "TYPICAL"
    result["cartea_zero_revision_class"] = "HIGH" if zero_revision == "FAVORABLE" else "LOW" if zero_revision == "UNFAVORABLE" else "TYPICAL"
    result["cartea_persistence_class"] = "HIGH" if persistence == "FAVORABLE" else "LOW" if persistence == "UNFAVORABLE" else "TYPICAL"
    if all(label == "FAVORABLE" for label in (activity, revision, zero_revision, persistence)):
        assessment = "REBATE_FAVORABLE"
    elif all(label == "UNFAVORABLE" for label in (activity, revision, zero_revision, persistence)):
        assessment = "REBATE_UNFAVORABLE"
    else:
        assessment = "MIXED_STATE"
    result["cartea_state_assessment"] = assessment
    result["cartea_state_statistics"] = current
    result["reasons"] = [
        "activity, zero-revision probability, revision volatility, and persistence are compared with observed cross-state baselines"
    ]
    return result
