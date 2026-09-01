"""Al Brooks' probability/reward/risk trader's-equation perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "brooks_trader_equation"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_trader_equation_probability",
    "brooks_trader_equation_reward",
    "brooks_trader_equation_risk",
    "brooks_trader_equation_cost",
    "brooks_trader_equation_unit",
    "brooks_trader_equation_data_provenance",
)


def _provenance_ok(value) -> bool:
    normalized = normalized_status(value)
    return normalized == "completed quote bar proxy" or explicitly_observed(
        value,
        accepted=("observed", "measured", "historical", "timestamped"),
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "brooks_trader_equation_data_provenance")):
        missing.append("brooks_trader_equation_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    probability = number(first(state, "brooks_trader_equation_probability"))
    reward = number(first(state, "brooks_trader_equation_reward"))
    risk = number(first(state, "brooks_trader_equation_risk"))
    cost = number(first(state, "brooks_trader_equation_cost"))
    unit = normalized_status(first(state, "brooks_trader_equation_unit"))
    if (
        probability is None
        or not 0.0 <= probability <= 1.0
        or reward is None
        or reward <= 0.0
        or risk is None
        or risk <= 0.0
        or cost is None
        or cost < 0.0
        or not unit
    ):
        result["brooks_trader_equation_assessment"] = "INVALID_EQUATION_INPUTS"
        result["reasons"] = ["probability, reward, risk, and same-unit cost must be finite and valid"]
        return result

    edge = probability * reward - (1.0 - probability) * risk - cost
    break_even = (risk + cost) / (reward + risk)
    result.update({
        "brooks_trader_equation_probability": probability,
        "brooks_trader_equation_reward": reward,
        "brooks_trader_equation_risk": risk,
        "brooks_trader_equation_cost": cost,
        "brooks_trader_equation_unit": unit,
        "brooks_trader_equation_edge": edge,
        "brooks_trader_equation_break_even_probability": break_even,
    })
    if edge > 0.0:
        result["brooks_trader_equation_assessment"] = "POSITIVE_AFTER_COST"
        result["reasons"] = ["probability-weighted reward exceeds probability-weighted risk and cost"]
    else:
        result["brooks_trader_equation_assessment"] = "NEGATIVE_AFTER_COST"
        result["reasons"] = ["probability-weighted reward does not exceed probability-weighted risk and cost"]
    result["warnings"] = ["the supplied probability is an estimate, not a certainty or a 95-percent entry gate"]
    return result
