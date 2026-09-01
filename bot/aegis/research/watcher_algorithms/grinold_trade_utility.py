"""Grinold-Kahn short-horizon trading utility diagnostic."""
from __future__ import annotations

from ._common import absent, base, first, number, explicitly_observed, values

ALGORITHM_ID = "grinold_trade_utility"
SOURCES = ("Richard Grinold and Ronald Kahn — Active Portfolio Management",)
KEYS = (
    "grinold_short_term_alpha_usd",
    "grinold_short_term_risk_adjustment_usd",
    "grinold_market_impact_usd",
    "grinold_trade_utility_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("short_term_alpha_risk_and_impact",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    alpha = number(first(state, "grinold_short_term_alpha_usd"))
    risk = number(first(state, "grinold_short_term_risk_adjustment_usd"))
    impact = number(first(state, "grinold_market_impact_usd"))
    provenance = first(state, "grinold_trade_utility_data_provenance")
    if alpha is None or risk is None or impact is None:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_short_term_alpha_risk_and_impact"]
        return result
    if risk < 0 or impact < 0:
        result["grinold_trade_utility_assessment"] = "INVALID_UTILITY_INPUT"
        result["reasons"] = ["risk adjustment and market impact must be non-negative"]
        return result
    if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "replay")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["grinold_trade_utility_data_provenance"]
        return result

    utility = alpha - risk - impact
    result["grinold_trade_utility_usd"] = utility
    result["grinold_short_term_alpha_usd"] = alpha
    result["grinold_short_term_risk_adjustment_usd"] = risk
    result["grinold_market_impact_usd"] = impact
    result["directional_claim"] = False
    if utility > 0:
        result["grinold_trade_utility_assessment"] = "POSITIVE_TRADING_UTILITY"
        result["reasons"] = ["short-term alpha exceeds the risk adjustment and market-impact cost"]
    else:
        result["grinold_trade_utility_assessment"] = "NEGATIVE_TRADING_UTILITY"
        result["reasons"] = ["short-term alpha does not exceed the risk adjustment and market-impact cost"]
    return result
