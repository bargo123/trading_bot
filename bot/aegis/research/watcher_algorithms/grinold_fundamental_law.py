"""Grinold and Kahn's skill-by-breadth information-ratio perspective."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "grinold_fundamental_law"
SOURCES = ("Richard Grinold, Ronald Kahn — Active Portfolio Management",)
KEYS = (
    "side",
    "grinold_information_coefficient",
    "grinold_breadth_per_year",
    "grinold_target_information_ratio",
    "grinold_fundamental_law_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "grinold_fundamental_law_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("grinold_fundamental_law_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    ic = number(first(state, "grinold_information_coefficient"))
    breadth = number(first(state, "grinold_breadth_per_year"))
    target = number(first(state, "grinold_target_information_ratio"))
    if (
        ic is None
        or breadth is None
        or target is None
        or not -1.0 <= ic <= 1.0
        or breadth <= 0.0
        or target < 0.0
    ):
        result["grinold_fundamental_law_action"] = "INVALID_FUNDAMENTAL_LAW_INPUT"
        result["reasons"] = [
            "information coefficient must be bounded, breadth positive, and target information ratio nonnegative"
        ]
        return result

    predicted = ic * math.sqrt(breadth)
    result.update({
        "grinold_predicted_information_ratio": predicted,
        "grinold_information_coefficient": ic,
        "grinold_breadth_per_year": breadth,
        "grinold_target_information_ratio": target,
        "directional_claim": False,
    })
    if predicted >= target:
        result["grinold_fundamental_law_action"] = "TARGET_WITHIN_SKILL_BREADTH_CAPACITY"
        result["reasons"] = ["observed skill and independent decision breadth support the stated target"]
    else:
        result["grinold_fundamental_law_action"] = "TARGET_EXCEEDS_SKILL_BREADTH_CAPACITY"
        result["reasons"] = ["the stated target exceeds the information ratio implied by observed skill and breadth"]
    return result
