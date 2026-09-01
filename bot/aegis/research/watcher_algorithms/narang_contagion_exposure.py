"""Narang's common-investor and strategy-overlap exposure warning."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "narang_contagion_exposure"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "side",
    "narang_strategy_overlap_score",
    "narang_strategy_overlap_limit",
    "narang_common_investor_exposure",
    "narang_common_investor_limit",
    "narang_contagion_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "narang_contagion_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("narang_contagion_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    overlap = number(first(state, "narang_strategy_overlap_score"))
    overlap_limit = number(first(state, "narang_strategy_overlap_limit"))
    common = number(first(state, "narang_common_investor_exposure"))
    common_limit = number(first(state, "narang_common_investor_limit"))
    if (
        overlap is None
        or overlap_limit is None
        or common is None
        or common_limit is None
        or not all(0.0 <= value <= 1.0 for value in (overlap, overlap_limit, common, common_limit))
    ):
        result["narang_contagion_action"] = "INVALID_CONTAGION_INPUT"
        result["reasons"] = ["overlap and common-investor exposures and limits must be finite fractions"]
        return result

    result.update({
        "narang_strategy_overlap_score": overlap,
        "narang_common_investor_exposure": common,
        "narang_contagion_alert_dimensions": [],
        "directional_claim": False,
    })
    if overlap > overlap_limit:
        result["narang_contagion_alert_dimensions"].append("strategy_overlap")
    if common > common_limit:
        result["narang_contagion_alert_dimensions"].append("common_investor_exposure")
    if result["narang_contagion_alert_dimensions"]:
        result["narang_contagion_action"] = "CONTAGION_ALERT"
        result["reasons"] = ["observed strategy overlap or common-investor exposure exceeds its explicit limit"]
    else:
        result["narang_contagion_action"] = "CONTAGION_WITHIN_LIMITS"
        result["reasons"] = ["observed strategy overlap and common-investor exposure remain within explicit limits"]
    return result
