"""Van Tharp market-selection filter for liquidity and usable volatility."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "tharp_market_selection"
SOURCES = ("Van K. Tharp — Trade Your Way to Financial Freedom",)
KEYS = (
    "tharp_liquidity_status",
    "tharp_volatility_reward_to_risk",
    "tharp_market_fit",
    "tharp_market_selection_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("liquidity_volatility_market_fit",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if not explicitly_observed(first(state, "tharp_market_selection_data_provenance"), accepted=("observed", "measured", "timestamped", "journal")):
        result["tharp_market_selection_assessment"] = "PROVENANCE_MISSING"
        result["warnings"] = ["market-selection filter is not supported by observed market data"]
        return result
    liquidity = normalized_status(first(state, "tharp_liquidity_status"))
    reward_to_risk = number(first(state, "tharp_volatility_reward_to_risk"))
    market_fit = normalized_status(first(state, "tharp_market_fit"))
    liquid = liquidity in {"liquid", "high liquidity", "adequate liquidity", "deep"}
    fit = market_fit in {"true", "yes", "fits", "fit", "fits trend criteria", "suitable", "appropriate"} or "fit" in market_fit or "suitable" in market_fit
    if reward_to_risk is None or reward_to_risk < 0:
        result["tharp_market_selection_assessment"] = "INVALID_VOLATILITY"
        result["reasons"] = ["volatility reward-to-initial-risk ratio is invalid"]
        return result
    if not liquid:
        result["tharp_market_selection_assessment"] = "LIQUIDITY_UNSUITABLE"
        result["warnings"] = ["the source treats wide spreads and illiquidity as a market-selection problem"]
        return result
    if reward_to_risk < 2.0:
        result["tharp_market_selection_assessment"] = "INSUFFICIENT_VOLATILITY"
        result["reasons"] = ["observed volatility does not offer the source's two-to-three initial-risk opportunity example"]
        return result
    if not fit:
        result["tharp_market_selection_assessment"] = "MARKET_CRITERIA_MISMATCH"
        result["reasons"] = ["the market does not fit the declared trading criteria"]
        return result
    result["tharp_market_selection_assessment"] = "MARKET_FITS"
    result["reasons"] = ["observed liquidity, usable volatility, and market-fit criteria are present"]
    return result
