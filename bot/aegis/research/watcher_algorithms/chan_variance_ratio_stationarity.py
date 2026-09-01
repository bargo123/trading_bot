"""Chan's variance-ratio stationarity diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "chan_variance_ratio_stationarity"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_variance_ratio",
    "chan_variance_ratio_null_rejected",
    "chan_variance_ratio_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "rejected", "reject", "significant"}:
        return True
    if label in {"false", "no", "not rejected", "not significant"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    ratio = number(first(state, "chan_variance_ratio"))
    rejected = _boolean(first(state, "chan_variance_ratio_null_rejected"))
    missing = [
        key for key, value in (
            ("chan_variance_ratio", ratio),
            ("chan_variance_ratio_null_rejected", rejected),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "chan_variance_ratio_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("chan_variance_ratio_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if ratio <= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["variance ratio must be positive"]
        return result
    if not rejected or abs(ratio - 1.0) < 1e-12:
        assessment = "RANDOM_WALK_NOT_REJECTED"
        reason = "the random-walk variance-ratio null was not rejected or the ratio is one"
    elif ratio < 1.0:
        assessment = "MEAN_REVERSION_SUPPORTED"
        reason = "a significant variance ratio below one indicates negative serial dependence"
    else:
        assessment = "TRENDING_SUPPORTED"
        reason = "a significant variance ratio above one indicates positive serial dependence"
    result["chan_variance_ratio_assessment"] = assessment
    result["chan_variance_ratio"] = ratio
    result["reasons"] = [reason]
    return result

