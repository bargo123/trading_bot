"""Leakage-aware chronological validation gate."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values

ALGORITHM_ID = "purged_walk_forward"
SOURCES = (
    "Marcos López de Prado — Advances in Financial Machine Learning",
    "David Aronson — Evidence-Based Technical Analysis",
    "Kevin J. Davey — Building Winning Algorithmic Trading Systems",
)
KEYS = ("validation_status", "purge_gap_s", "max_label_horizon_s", "embargo_s", "validation_splits")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("purged_chronological_validation",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    status = strings(state, "validation_status")
    purge = number(first(state, "purge_gap_s"))
    horizon = number(first(state, "max_label_horizon_s"))
    embargo = number(first(state, "embargo_s"))
    splits = number(first(state, "validation_splits"))
    if "purged" not in status or "unpurged" in status or "not purged" in status or None in {purge, horizon, embargo, splits}:
        result["view"] = "WAIT"
        result["reasons"] = ["purged walk-forward status and all leakage controls must be recorded"]
        return result
    if purge < horizon or embargo < 0 or splits < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["purge gap must cover the maximum label horizon and use at least two splits"]
        return result
    result["validation_assessment"] = "LEAKAGE_CONTROLS_PRESENT"
    result["view"] = "WAIT"
    result["reasons"] = ["validation context is sound but has no directional trading authority"]
    return result
