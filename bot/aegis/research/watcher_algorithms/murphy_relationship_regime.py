"""Adaptive guard for weakening or changing intermarket relationships."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "murphy_relationship_regime"
SOURCES = ("Trading with Intermarket Analysis",)
KEYS = (
    "murphy_current_correlation",
    "murphy_baseline_correlation",
    "murphy_relationship_state",
    "murphy_relationship_observation_n",
    "murphy_relationship_regime_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and "correlation" in label


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "murphy_relationship_regime_provenance")):
        missing.append("murphy_relationship_regime_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    current = number(first(state, "murphy_current_correlation"))
    baseline = number(first(state, "murphy_baseline_correlation"))
    observations = number(first(state, "murphy_relationship_observation_n"))
    status = normalized_status(first(state, "murphy_relationship_state"))
    if None in {current, baseline, observations} or not -1 <= current <= 1 or not -1 <= baseline <= 1 or observations <= 0:
        result["murphy_relationship_assessment"] = "UNKNOWN"
        result["reasons"] = ["relationship regime requires finite correlations in [-1, 1] and observations"]
        return result
    if status in {"weakening", "broken", "changed"}:
        result["murphy_relationship_assessment"] = "WEAKENING"
        result["murphy_downweight_relationship"] = True
        result["warnings"] = ["the source says changing correlations should be downweighted until they strengthen"]
    elif status in {"stable", "strengthening"}:
        result["murphy_relationship_assessment"] = "STABLE"
        result["murphy_downweight_relationship"] = False
    else:
        result["murphy_relationship_assessment"] = "UNKNOWN"
        result["murphy_downweight_relationship"] = True
    result["reasons"] = ["intermarket relationships are adaptive context rather than permanent rules"]
    return result
