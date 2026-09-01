"""Clenow's ATR-normalized theoretical position-impact calculation."""
from __future__ import annotations

import math

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "clenow_atr_impact_sizing"
SOURCES = ("Following the Trend — Diversified Managed Futures Trading",)
KEYS = (
    "clenow_equity_usd",
    "clenow_atr",
    "clenow_point_value",
    "clenow_risk_factor",
    "clenow_sizing_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "clenow_sizing_data_provenance"),
        accepted=("observed", "timestamped"),
    ):
        missing.append("clenow_sizing_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    equity = number(first(state, "clenow_equity_usd"))
    atr = number(first(state, "clenow_atr"))
    point_value = number(first(state, "clenow_point_value"))
    risk_factor = number(first(state, "clenow_risk_factor"))
    if any(value is None for value in (equity, atr, point_value, risk_factor)) or any(
        value <= 0 for value in (equity, atr, point_value, risk_factor)
    ):
        result["clenow_sizing_assessment"] = "INVALID_VOLATILITY_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["equity, ATR, point value, and risk factor must be positive finite values"]
        return result

    target_impact = equity * risk_factor
    contract_impact = atr * point_value
    contracts = math.floor(target_impact / contract_impact)
    result["clenow_target_impact_usd"] = target_impact
    result["clenow_theoretical_impact_usd"] = contracts * contract_impact
    result["clenow_contract_impact_usd"] = contract_impact
    result["clenow_recommended_contracts"] = contracts
    result["clenow_sizing_assessment"] = (
        "VOLATILITY_NORMALIZED_SIZE" if contracts > 0 else "NO_WHOLE_CONTRACT_WITHIN_TARGET"
    )
    result["view"] = "WAIT"
    result["reasons"] = ["size is a volatility-normalized research diagnostic, not an order instruction"]
    return result
