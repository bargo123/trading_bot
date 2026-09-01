"""Velu, Hardy, and Nehren's square-root transaction-cost hurdle."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, values, with_direction

ALGORITHM_ID = "velu_square_root_cost_hurdle"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_order_size",
    "velu_average_daily_volume",
    "velu_volatility",
    "velu_spread",
    "velu_impact_alpha",
    "velu_spread_beta",
    "velu_expected_gross_return",
    "velu_tcost_model_status",
    "velu_tcost_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_tcost_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_tcost_data_provenance")
    if not explicitly_validated(first(state, "velu_tcost_model_status")):
        missing.append("velu_tcost_model_status")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    order_size = number(first(state, "velu_order_size"))
    average_daily_volume = number(first(state, "velu_average_daily_volume"))
    volatility = number(first(state, "velu_volatility"))
    spread = number(first(state, "velu_spread"))
    impact_alpha = number(first(state, "velu_impact_alpha"))
    spread_beta = number(first(state, "velu_spread_beta"))
    gross_return = number(first(state, "velu_expected_gross_return"))
    if (
        order_size is None
        or average_daily_volume is None
        or volatility is None
        or spread is None
        or impact_alpha is None
        or spread_beta is None
        or gross_return is None
        or order_size <= 0
        or average_daily_volume <= 0
        or volatility < 0
        or spread < 0
        or impact_alpha < 0
        or spread_beta < 0
    ):
        result["velu_tcost_action"] = "INVALID_TCOST_INPUT"
        result["reasons"] = [
            "the square-root cost model needs positive order/ADV and nonnegative volatility, spread, and coefficients"
        ]
        return result

    relative_size = order_size / average_daily_volume
    impact_cost = impact_alpha * volatility * math.sqrt(relative_size)
    spread_cost = spread_beta * spread
    total_cost = impact_cost + spread_cost
    net_return = gross_return - total_cost
    result.update(
        {
            "velu_relative_order_size": relative_size,
            "velu_estimated_impact_cost": impact_cost,
            "velu_estimated_spread_cost": spread_cost,
            "velu_estimated_total_cost": total_cost,
            "velu_expected_net_return": net_return,
        }
    )
    if net_return <= 0:
        result["velu_tcost_action"] = "COST_HURDLE_FAIL"
        result["reasons"] = [
            "expected gross return does not exceed the validated square-root impact plus spread cost"
        ]
        return result
    result["velu_tcost_action"] = "NET_EDGE_AFTER_SQRT_IMPACT"
    return with_direction(
        result,
        state,
        first(state, "side").upper(),
        "expected gross return exceeds the validated square-root impact and spread cost",
    )
