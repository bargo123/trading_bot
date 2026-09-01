"""Jeremy du Plessis' stronger three-box Point-and-Figure triple signal."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_triple_top_bottom"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 123-125"
KEYS = (
    "pf_box_reversal",
    "pf_pattern_type",
    "pf_triple_level_tests",
    "pf_breakout_direction",
    "pf_breakout_confirmed",
    "pf_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("pf_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "pf_box_reversal")) != "3 box":
        result["view"] = "WAIT"
        result["reasons"] = ["the source triple-top/bottom signal is a three-box pattern"]
        return result
    pattern = normalized_status(first(state, "pf_pattern_type"))
    if pattern not in {"triple top", "triple bottom"}:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed pattern is not a triple-top or triple-bottom"]
        return result
    tests = number(first(state, "pf_triple_level_tests"))
    if tests is None or tests < 2 or tests != int(tests):
        result["view"] = "WAIT"
        result["reasons"] = ["a triple signal requires two prior tests of the breached level"]
        return result
    if not _truthy(first(state, "pf_breakout_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the triple-top/bottom breakout is not confirmed"]
        return result
    direction = normalized_status(first(state, "pf_breakout_direction"))
    if pattern == "triple top" and direction == "up":
        signal = "BUY"
    elif pattern == "triple bottom" and direction == "down":
        signal = "SELL"
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["triple-top/bottom type and breakout direction do not agree"]
        return result
    result["pf_triple_level_tests"] = int(tests)
    return with_direction(result, state, signal, "confirmed Point-and-Figure triple-top/bottom breakout")
