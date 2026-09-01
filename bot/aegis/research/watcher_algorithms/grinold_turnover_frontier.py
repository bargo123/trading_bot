"""Grinold and Kahn's marginal value-added versus turnover-cost rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "grinold_turnover_frontier"
SOURCES = ("Richard Grinold, Ronald Kahn — Active Portfolio Management",)
KEYS = (
    "side",
    "grinold_marginal_value_added",
    "grinold_marginal_transaction_cost",
    "grinold_turnover_fraction",
    "grinold_turnover_limit",
    "grinold_turnover_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "grinold_turnover_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("grinold_turnover_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    value_added = number(first(state, "grinold_marginal_value_added"))
    transaction_cost = number(first(state, "grinold_marginal_transaction_cost"))
    turnover = number(first(state, "grinold_turnover_fraction"))
    turnover_limit = number(first(state, "grinold_turnover_limit"))
    if (
        value_added is None
        or transaction_cost is None
        or turnover is None
        or turnover_limit is None
        or transaction_cost < 0.0
        or turnover < 0.0
        or turnover_limit <= 0.0
    ):
        result["grinold_turnover_action"] = "INVALID_TURNOVER_INPUT"
        result["reasons"] = [
            "marginal turnover inputs require finite value, nonnegative cost, and a positive limit"
        ]
        return result
    result.update({
        "grinold_marginal_value_added": value_added,
        "grinold_marginal_transaction_cost": transaction_cost,
        "grinold_turnover_fraction": turnover,
        "grinold_turnover_limit": turnover_limit,
        "directional_claim": False,
    })
    if turnover > turnover_limit:
        result["grinold_turnover_action"] = "TURNOVER_LIMIT_EXCEEDED"
        result["reasons"] = ["the proposed turnover exceeds the supplied turnover limit"]
    elif value_added > transaction_cost:
        result["grinold_turnover_action"] = "MARGINAL_VALUE_CLEARS_COST"
        result["reasons"] = ["marginal expected value added exceeds marginal transaction cost"]
    else:
        result["grinold_turnover_action"] = "MARGINAL_COST_EXCEEDS_VALUE"
        result["reasons"] = ["marginal transaction cost is not below marginal expected value added"]
    return result
