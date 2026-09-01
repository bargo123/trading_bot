"""Carver's cost-based trading-speed limit as a read-only filter."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "carver_speed_limit"
SOURCES = ("Robert Carver — Systematic Trading",)
KEYS = (
    "carver_standardized_cost_sr",
    "carver_turnover_per_year",
    "carver_expected_pre_cost_sr",
    "carver_max_cost_fraction",
    "carver_speed_data_provenance",
)


def _observed(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in provenance for token in ("observed", "historical", "live", "broker"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _observed(first(state, "carver_speed_data_provenance")):
        missing.append("carver_speed_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    cost = number(first(state, "carver_standardized_cost_sr"))
    turnover = number(first(state, "carver_turnover_per_year"))
    pre_cost = number(first(state, "carver_expected_pre_cost_sr"))
    fraction = number(first(state, "carver_max_cost_fraction"))
    if None in (cost, turnover, pre_cost, fraction) or cost < 0 or turnover < 0 or pre_cost <= 0 or not 0 < fraction <= 1:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_cost_turnover_edge_budget"]
        return result

    annualized_cost = cost * turnover
    cost_budget = pre_cost * fraction
    max_turnover = cost_budget / cost if cost > 0 else None
    result.update({
        "carver_annualized_cost_sr": annualized_cost,
        "carver_cost_budget_sr": cost_budget,
        "carver_max_turnover": max_turnover,
        "directional_claim": False,
    })
    if annualized_cost > cost_budget:
        result["carver_speed_action"] = "SPEED_LIMIT_EXCEEDED"
        result["reasons"] = ["annualized standardized costs exceed the permitted share of pre-cost edge"]
    else:
        result["carver_speed_action"] = "SPEED_WITHIN_COST_BUDGET"
        result["reasons"] = ["annualized standardized costs remain within the permitted share of pre-cost edge"]
    return result
