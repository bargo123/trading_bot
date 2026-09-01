"""Market-impact and liquidity-cost context."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "market_impact"
SOURCES = (
    "Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",
    "Jean-Philippe Bouchaud et al. — Trades, Quotes and Prices",
    "Irene Aldridge — High-Frequency Trading",
)
KEYS = ("order_size", "average_daily_volume", "spread", "estimated_market_impact", "impact_model_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_market_impact_estimate",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    size = number(first(state, "order_size"))
    adv = number(first(state, "average_daily_volume"))
    spread = number(first(state, "spread", "spread_price"))
    impact = number(first(state, "estimated_market_impact"))
    status = first(state, "impact_model_status")
    if None in {size, adv, spread, impact} or size < 0 or adv <= 0 or spread < 0 or impact < 0 or not explicitly_validated(status):
        result["view"] = "WAIT"
        result["reasons"] = ["market-impact context requires a validated cost model and valid liquidity inputs"]
        return result
    result["size_to_adv"] = size / adv
    result["impact_assessment"] = "LOW" if impact <= spread else "HIGH"
    result["view"] = "WAIT"
    result["reasons"] = ["market impact is a cost/risk diagnostic and cannot select a direction"]
    return result
