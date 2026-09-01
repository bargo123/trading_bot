"""Jeremy du Plessis' Point-and-Figure bull/bear-trap perspective.

A trap is only identifiable after the opposite signal has actually appeared.
The Watcher therefore keeps the initial signal pending and records the
reversal only when the opposing Point-and-Figure signal is confirmed.
"""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pf_trap_reversal"
SOURCES = ("Jeremy du Plessis — The Definitive Guide to Point and Figure",)
SOURCE_PAGES = "pp. 145-146"
KEYS = (
    "pf_trap_type",
    "pf_initial_signal",
    "pf_reversal_signal",
    "pf_reversal_confirmed",
    "pf_pattern_depth_boxes",
    "pf_data_provenance",
)


def _truthy(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, KEYS)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    provenance = normalized_status(first(state, "pf_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["observed_point_and_figure_chart"]
        result["reasons"] = ["trap analysis requires observed Point-and-Figure chart provenance"]
        return result

    trap_type = normalized_status(first(state, "pf_trap_type")).replace(" ", "_")
    initial = normalized_status(first(state, "pf_initial_signal")).upper()
    reversal = normalized_status(first(state, "pf_reversal_signal")).upper()
    depth = number(first(state, "pf_pattern_depth_boxes"))
    if trap_type not in {"bull_trap", "bear_trap"} or initial not in {"BUY", "SELL"} or reversal not in {"BUY", "SELL"}:
        result["view"] = "WAIT"
        result["reasons"] = ["trap type and both Point-and-Figure signals must be explicit"]
        return result
    if depth is None or depth <= 0 or not depth.is_integer():
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["positive_pattern_depth_boxes"]
        result["reasons"] = ["trap depth must be a positive whole number of observed boxes"]
        return result
    expected = ("BUY", "SELL") if trap_type == "bull_trap" else ("SELL", "BUY")
    if (initial, reversal) != expected:
        result["view"] = "WAIT"
        result["reasons"] = ["the recorded signals do not form the source's bull-trap or bear-trap reversal"]
        return result

    result["pf_trap_depth_boxes"] = int(depth)
    result["pf_trap_initial_signal"] = initial
    result["pf_trap_reversal_signal"] = reversal
    if not _truthy(first(state, "pf_reversal_confirmed")):
        result["pf_trap_assessment"] = "TRAP_PENDING_OPPOSITE_CONFIRMATION"
        result["view"] = "WAIT"
        result["reasons"] = ["the initial trap signal must not be pre-empted before the opposite signal is confirmed"]
        return result

    result["pf_trap_assessment"] = "BULL_TRAP_CONFIRMED" if trap_type == "bull_trap" else "BEAR_TRAP_CONFIRMED"
    return with_direction(
        result,
        state,
        reversal,
        "the observed opposite Point-and-Figure signal confirms the trap reversal",
    )
