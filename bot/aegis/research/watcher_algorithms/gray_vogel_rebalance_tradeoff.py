"""Gray--Vogel momentum portfolio-construction trade-off perspective.

The source compares concentration and rebalance frequency, but also stresses
that the apparent gross advantage must survive trading costs.  This module is
portfolio context only: it never creates a directional signal or an order.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values


ALGORITHM_ID = "gray_vogel_rebalance_tradeoff"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "gray_rebalance_portfolio_size",
    "gray_rebalance_universe_size",
    "gray_rebalance_holding_months",
    "gray_rebalance_frequency_months",
    "gray_rebalance_expected_gross_edge",
    "gray_rebalance_cost_per_rebalance",
    "gray_rebalance_concentration_cutoff",
    "gray_rebalance_overlapping_portfolios",
    "gray_rebalance_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "gray_rebalance_data_provenance"),
        accepted=("observed", "measured", "historical"),
    ):
        missing.append("gray_rebalance_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    size = number(first(state, "gray_rebalance_portfolio_size"))
    universe = number(first(state, "gray_rebalance_universe_size"))
    holding = number(first(state, "gray_rebalance_holding_months"))
    frequency = number(first(state, "gray_rebalance_frequency_months"))
    gross_edge = number(first(state, "gray_rebalance_expected_gross_edge"))
    cost = number(first(state, "gray_rebalance_cost_per_rebalance"))
    concentration_cutoff = number(first(state, "gray_rebalance_concentration_cutoff"))
    overlapping = first(state, "gray_rebalance_overlapping_portfolios")
    if (
        any(value is None for value in (size, universe, holding, frequency, gross_edge, cost, concentration_cutoff))
        or not size.is_integer()
        or not universe.is_integer()
        or size <= 0
        or universe <= 0
        or size > universe
        or holding <= 0
        or frequency <= 0
        or gross_edge <= 0
        or cost < 0
        or not 0 < concentration_cutoff <= 1
        or not isinstance(overlapping, bool)
    ):
        result["gray_rebalance_assessment"] = "INVALID_REBALANCE_INPUT"
        result["reasons"] = ["portfolio size, universe, holding/rebalance cadence, edge, cost, cutoff, and overlap state must be finite and coherent"]
        return result

    concentration_ratio = size / universe
    net_edge = gross_edge - cost
    result.update({
        "gray_rebalance_portfolio_size": int(size),
        "gray_rebalance_universe_size": int(universe),
        "gray_rebalance_concentration_ratio": concentration_ratio,
        "gray_rebalance_net_edge": net_edge,
    })
    if holding > frequency and not overlapping:
        result["gray_rebalance_assessment"] = "OVERLAP_REQUIRED"
        result["warnings"] = ["the source uses overlapping portfolios when a holding period spans multiple rebalance dates"]
        result["reasons"] = ["multi-period holding without an observed overlapping-portfolio construction is not comparable"]
        return result
    if net_edge <= 0:
        result["gray_rebalance_assessment"] = "COST_DOMINATES"
        result["warnings"] = ["gross momentum advantage does not cover the supplied rebalance cost"]
        result["reasons"] = ["portfolio construction must be evaluated after estimated trading costs"]
        return result
    if concentration_ratio <= concentration_cutoff and frequency <= holding:
        result["gray_rebalance_assessment"] = "CONCENTRATED_FREQUENT_REBALANCE"
        result["reasons"] = ["the observed construction is concentrated and rebalances at least as frequently as its holding period"]
    else:
        result["gray_rebalance_assessment"] = "DIVERSIFIED_OR_SLOW_REBALANCE"
        result["warnings"] = ["the observed construction does not match the source's concentrated/frequent momentum construction"]
        result["reasons"] = ["concentration and cadence are descriptive portfolio context, not a directional entry signal"]
    return result
