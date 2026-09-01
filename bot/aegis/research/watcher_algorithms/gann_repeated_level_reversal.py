"""W. D. Gann's repeated double/triple top and bottom reversal rule."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "gann_repeated_level_reversal"
SOURCES = ("W. D. Gann — How to Make Profits in Commodities",)
SOURCE_PAGES = "pp. 31-32, 43-46"
KEYS = (
    "gann_repeated_level_type",
    "gann_repeated_level_tests",
    "gann_repeated_level_break",
    "gann_repeated_level_confirmed",
    "gann_repeated_level_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "gann_repeated_level_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("gann_repeated_level_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    tests = number(first(state, "gann_repeated_level_tests"))
    if tests is None or tests < 2 or tests != int(tests):
        result["view"] = "WAIT"
        result["reasons"] = ["a repeated Gann level requires at least two prior observed tests"]
        return result
    if not volman_truth(first(state, "gann_repeated_level_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the repeated-level break is not confirmed"]
        return result

    level_type = normalized_status(first(state, "gann_repeated_level_type"))
    breaking = normalized_status(first(state, "gann_repeated_level_break"))
    if level_type == "bottom" and breaking == "up":
        signal = "BUY"
    elif level_type == "top" and breaking == "down":
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["the repeated level and confirmed break direction do not form a reversal"]
        return result

    result["gann_repeated_level_tests"] = int(tests)
    result["gann_repeated_level_strength"] = "TRIPLE_LEVEL" if tests >= 3 else "DOUBLE_LEVEL"
    return with_direction(result, state, signal, "a confirmed break from a repeatedly tested Gann top/bottom level")
