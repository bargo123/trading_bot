"""Scenario/stress risk perspective grounded in Quantum Finance's risk chapters."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "quantum_finance_scenario_stress"
SOURCES = ("Hayden Van Der Post — Quantum Finance",)
KEYS = ("qf_scenario_pnl", "qf_risk_budget", "qf_scenario_data_provenance")


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(token in label for token in ("unknown", "unavailable", "fabricated")) and any(
        token in label for token in ("historical", "timestamped", "scenario", "simulation")
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "qf_scenario_data_provenance")):
        missing.append("qf_scenario_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    scenarios = first(state, "qf_scenario_pnl")
    budget = number(first(state, "qf_risk_budget"))
    if isinstance(scenarios, (str, bytes, bytearray)) or not isinstance(scenarios, Sequence) or budget is None or budget <= 0:
        result["quantum_finance_scenario_assessment"] = "INVALID_SCENARIOS"
        result["reasons"] = ["stress analysis requires a finite scenario sequence and a positive risk budget"]
        return result
    pnl = [number(value) for value in scenarios]
    if not pnl or any(value is None for value in pnl):
        result["quantum_finance_scenario_assessment"] = "INVALID_SCENARIOS"
        result["reasons"] = ["scenario outcomes must be finite numeric values; missing values are not imputed"]
        return result
    worst = min(pnl)
    result["scenario_count"] = len(pnl)
    result["worst_case_pnl"] = worst
    result["mean_scenario_pnl"] = sum(pnl) / len(pnl)
    result["implementation_class"] = "CLASSICAL_SCENARIO_ANALOGUE"
    result["quantum_execution_claim"] = False
    if worst < -budget:
        result["quantum_finance_scenario_assessment"] = "STRESS_EXCEEDS_BUDGET"
        result["reasons"] = ["the worst supplied scenario exceeds the stated risk budget"]
    else:
        result["quantum_finance_scenario_assessment"] = "WITHIN_BUDGET"
        result["reasons"] = ["the supplied scenario set remains within the stated risk budget"]
    return result

