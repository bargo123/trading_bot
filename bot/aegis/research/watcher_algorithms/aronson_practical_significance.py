"""Aronson practical-versus-statistical significance perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction
from ._deprado_common import provenance_ok

ALGORITHM_ID = "aronson_practical_significance"
SOURCES = ("David Aronson — Evidence-Based Technical Analysis",)
KEYS = (
    "aronson_rule_direction",
    "aronson_observed_net_expectancy",
    "aronson_practical_edge_floor",
    "aronson_costs_included",
    "aronson_data_provenance",
)


def evaluate(state):
    expectancy = number(first(state, "aronson_observed_net_expectancy"))
    floor = number(first(state, "aronson_practical_edge_floor"))
    direction = str(first(state, "aronson_rule_direction") or "").strip().upper()
    found = values(state, *KEYS)
    missing = []
    if expectancy is None:
        missing.append("aronson_observed_net_expectancy")
    if floor is None or floor < 0:
        missing.append("aronson_practical_edge_floor")
    if first(state, "aronson_costs_included") is None:
        missing.append("aronson_costs_included")
    if direction not in {"BUY", "SELL"}:
        missing.append("aronson_rule_direction")
    provenance = first(state, "aronson_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("aronson_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["analysis_stage"] = "after_cost_economic_validation"
    result["directional_claim"] = False
    result["aronson_observed_net_expectancy"] = expectancy
    result["aronson_practical_edge_floor"] = floor
    if first(state, "aronson_costs_included") is not True:
        result["aronson_practical_assessment"] = "COSTS_NOT_INCLUDED"
        result["reasons"] = ["practical value cannot be assessed before spread and execution costs are included"]
        return result
    supported = expectancy > floor
    result["aronson_practical_assessment"] = "PRACTICALLY_SIGNIFICANT" if supported else "NOT_PRACTICALLY_SIGNIFICANT"
    result["warnings"] = ["practical significance is distinct from statistical significance and execution authority"]
    if supported:
        result["directional_claim"] = True
        return with_direction(result, state, direction, "after-cost expectancy exceeds the explicit practical edge floor")
    result["reasons"] = ["after-cost expectancy does not exceed the explicit practical edge floor"]
    return result
