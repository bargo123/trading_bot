"""W. D. Gann's fourth-time-at-the-same-level reversal rule."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "gann_fourth_level_reversal"
SOURCES = ("W. D. Gann — How to Make Profits in Commodities",)
SOURCE_PAGES = "pp. 43-46"
KEYS = (
    "gann_fourth_level_type",
    "gann_fourth_level_tests",
    "gann_fourth_level_break",
    "gann_fourth_level_confirmed",
    "gann_fourth_level_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "gann_fourth_level_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("gann_fourth_level_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    tests = number(first(state, "gann_fourth_level_tests"))
    if tests is None or tests < 4 or tests != int(tests):
        result["view"] = "WAIT"
        result["reasons"] = ["the fourth-level rule requires four observed approaches to the same level"]
        return result
    if not volman_truth(first(state, "gann_fourth_level_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the fourth approach and break are not confirmed"]
        return result
    level_type = normalized_status(first(state, "gann_fourth_level_type"))
    breaking = normalized_status(first(state, "gann_fourth_level_break"))
    if level_type == "top" and breaking == "down":
        signal = "SELL"
        assessment = "FOURTH_TOP_REVERSAL"
    elif level_type == "bottom" and breaking == "up":
        signal = "BUY"
        assessment = "FOURTH_BOTTOM_REVERSAL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the fourth same-level test has no matching reversal break"]
        return result
    result["gann_fourth_level_assessment"] = assessment
    result["gann_fourth_level_tests"] = int(tests)
    return with_direction(result, state, signal, "the fourth observed approach to the same level confirmed a major reversal direction")
