"""Jeremy du Plessis' three-box Point-and-Figure catapult perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_three_box_catapult"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
KEYS = (
    "pf_box_reversal",
    "pf_pattern_type",
    "pf_initial_breakout_boxes",
    "pf_pullback_into_pattern",
    "pf_pullback_reverse_signal",
    "pf_second_breakout_beyond_initial",
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
        result["reasons"] = ["the source catapult rule is the three-box reversal pattern"]
        return result
    pattern = normalized_status(first(state, "pf_pattern_type"))
    if pattern not in {"triple top", "multiple top", "triple bottom", "multiple bottom"}:
        result["view"] = "WAIT"
        result["reasons"] = ["a three-box catapult requires a triple or multiple top/bottom breakout"]
        return result
    boxes = number(first(state, "pf_initial_breakout_boxes"))
    if boxes is None or not 1 <= boxes <= 3:
        result["view"] = "WAIT"
        result["reasons"] = ["the initial breakout must be one to three boxes"]
        return result
    if not _truthy(first(state, "pf_pullback_into_pattern")):
        result["view"] = "WAIT"
        result["reasons"] = ["the first breakout has not pulled back into the pattern"]
        return result
    if _truthy(first(state, "pf_pullback_reverse_signal")):
        result["view"] = "WAIT"
        result["reasons"] = ["an opposite signal during the pullback invalidates the catapult"]
        return result
    if not _truthy(first(state, "pf_second_breakout_beyond_initial")):
        result["view"] = "WAIT"
        result["reasons"] = ["the reassertion breakout has not exceeded the initial breakout"]
        return result
    signal = "BUY" if pattern in {"triple top", "multiple top"} else "SELL"
    result["pf_catapult_geometry"] = {
        "initial_breakout_boxes": boxes,
        "pullback_into_pattern": True,
        "second_breakout_beyond_initial": True,
    }
    return with_direction(result, state, signal, "the three-box pattern shows breakout, non-reversing pullback, and reassertion")
