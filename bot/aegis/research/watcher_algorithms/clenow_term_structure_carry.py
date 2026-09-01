"""Clenow's weekly futures term-structure carry perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "clenow_term_structure_carry"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_curve_state",
    "clenow_steepest_annualized_carry",
    "clenow_carry_liquidity_sufficient",
    "clenow_weekly_rebalance",
    "clenow_carry_data_provenance",
)


def _truth(value: object) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "present", "valid", "sufficient"}


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "clenow_carry_data_provenance"),
        accepted=("observed", "measured", "timestamped"),
    ):
        missing.append("clenow_carry_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    curve = normalized_status(first(state, "clenow_curve_state"))
    carry = number(first(state, "clenow_steepest_annualized_carry"))
    if carry is None or curve not in {"contango", "backwardation"}:
        result["reasons"] = ["the futures curve must be observed as contango or backwardation with finite annualized carry"]
        return result
    if not _truth(first(state, "clenow_carry_liquidity_sufficient")):
        result["reasons"] = ["the steepest curve point does not have sufficient observed liquidity"]
        return result
    if not _truth(first(state, "clenow_weekly_rebalance")):
        result["reasons"] = ["the source model evaluates term structure on its weekly rebalance"]
        return result

    if curve == "contango":
        threshold = 0.15
        result["clenow_carry_threshold"] = threshold
        if carry <= -threshold:
            return with_direction(result, state, "SELL", "liquid contango exceeds the source's 15% annualized short threshold")
        result["reasons"] = ["contango is not steep enough for the source's 15% annualized short threshold"]
        return result

    threshold = 0.075
    result["clenow_carry_threshold"] = threshold
    if carry >= threshold:
        return with_direction(result, state, "BUY", "liquid backwardation exceeds the source's 7.5% annualized long threshold")
    result["reasons"] = ["backwardation is not steep enough for the source's 7.5% annualized long threshold"]
    return result
