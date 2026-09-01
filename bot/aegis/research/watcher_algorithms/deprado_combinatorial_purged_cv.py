"""Chronological combinatorial purged cross-validation diagnostics."""
from __future__ import annotations

from itertools import combinations
from math import comb

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "deprado_combinatorial_purged_cv"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_group_count",
    "deprado_test_group_count",
    "deprado_purge_group_count",
    "deprado_embargo_group_count",
    "deprado_cpcv_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    group_count = number(first(state, "deprado_group_count"))
    test_count = number(first(state, "deprado_test_group_count"))
    purge_count = number(first(state, "deprado_purge_group_count"))
    embargo_count = number(first(state, "deprado_embargo_group_count"))
    missing = [
        key for key, value in (
            ("deprado_group_count", group_count),
            ("deprado_test_group_count", test_count),
            ("deprado_purge_group_count", purge_count),
            ("deprado_embargo_group_count", embargo_count),
        ) if value is None
    ]
    if not explicitly_observed(
        first(state, "deprado_cpcv_data_provenance"),
        accepted=("observed", "measured", "replay"),
    ):
        missing.append("deprado_cpcv_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    if any(
        not value.is_integer() or value < 0
        for value in (group_count, test_count, purge_count, embargo_count)
    ) or group_count < 2 or test_count < 1 or test_count >= group_count:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["CPCV group counts must be integers with 1 <= test groups < total groups"]
        return result

    groups = range(int(group_count))
    splits = []
    for test_groups_tuple in combinations(groups, int(test_count)):
        test_groups = list(test_groups_tuple)
        train_groups = []
        purged_groups = []
        for group in groups:
            if group in test_groups:
                continue
            is_purged = any(
                test_group - int(purge_count) <= group <= test_group + int(purge_count) + int(embargo_count)
                for test_group in test_groups
            )
            if is_purged:
                purged_groups.append(group)
            else:
                train_groups.append(group)
        splits.append({
            "test_groups": test_groups,
            "train_groups": train_groups,
            "purged_or_embargoed_groups": purged_groups,
        })

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["deprado_cpcv_split_count"] = comb(int(group_count), int(test_count))
    result["deprado_cpcv_splits"] = splits
    result["deprado_cpcv_assessment"] = "PURGED_COMBINATORIAL_SPLITS"
    result["warnings"] = ["CPCV is a validation design and does not authorize a trade"]
    return result
