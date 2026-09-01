"""Dalton/Steidlmayer single-print shallow-retest perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "dalton_single_print_retest"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Peter Steidlmayer — Steidlmayer on Markets",
)
SOURCE_PAGES = "pp. 171-176"
KEYS = (
    "dalton_single_print_origin",
    "dalton_single_print_retrace_depth_percent",
    "dalton_single_print_retest_is_shallow",
    "dalton_single_print_area_held",
    "dalton_single_print_close_direction",
    "dalton_single_print_confirmed",
    "dalton_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "dalton_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("dalton_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    origin = normalized_status(first(state, "dalton_single_print_origin"))
    depth = number(first(state, "dalton_single_print_retrace_depth_percent"))
    close_direction = normalized_status(first(state, "dalton_single_print_close_direction"))
    if origin not in {"up", "down"} or close_direction not in {"up", "down"} or depth is None or not 0.0 <= depth <= 100.0:
        result["view"] = "WAIT"
        result["reasons"] = ["single-print origin, retrace depth, and close direction must be explicit finite observations"]
        return result
    if not volman_truth(first(state, "dalton_single_print_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the single-print retest is not confirmed"]
        return result
    if not volman_truth(first(state, "dalton_single_print_retest_is_shallow")) or not volman_truth(first(state, "dalton_single_print_area_held")):
        result["view"] = "WAIT"
        result["reasons"] = ["a shallow, held single-print area is required; a deep or failed fill is not a signal"]
        return result
    if close_direction != origin:
        result["view"] = "WAIT"
        result["reasons"] = ["the retest close does not preserve the single-print origin direction"]
        return result
    if origin == "up":
        result["dalton_single_print_assessment"] = "SHALLOW_SUPPORT_RETEST"
        return with_direction(result, state, "BUY", "the upside single-print area held on a shallow retest")
    result["dalton_single_print_assessment"] = "SHALLOW_RESISTANCE_RETEST"
    return with_direction(result, state, "SELL", "the downside single-print area held on a shallow retest")
