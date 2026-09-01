"""Aldridge event/risk-arbitrage expected-value perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction
from ._deprado_common import provenance_ok

ALGORITHM_ID = "aldridge_risk_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_risk_arbitrage_probability", "aldridge_risk_arbitrage_profit_if_success", "aldridge_risk_arbitrage_loss_if_failure", "aldridge_risk_arbitrage_cost_per_trade", "aldridge_risk_arbitrage_direction", "aldridge_risk_arbitrage_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = first(state, "aldridge_risk_arbitrage_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("aldridge_risk_arbitrage_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    probability = number(first(state, "aldridge_risk_arbitrage_probability"))
    profit = number(first(state, "aldridge_risk_arbitrage_profit_if_success"))
    loss = number(first(state, "aldridge_risk_arbitrage_loss_if_failure"))
    cost = number(first(state, "aldridge_risk_arbitrage_cost_per_trade"))
    direction = normalized_status(first(state, "aldridge_risk_arbitrage_direction")).upper()
    if None in {probability, profit, loss, cost} or not 0 <= probability <= 1 or profit <= 0 or loss <= 0 or cost < 0 or direction not in {"BUY", "SELL"}:
        result["reasons"] = ["risk arbitrage requires bounded probability, positive payoff/loss, non-negative cost, and direction"]
        return result
    edge = probability * profit - (1 - probability) * loss - cost
    result["aldridge_risk_arbitrage_expected_net_edge"] = edge
    if edge <= 0:
        result["reasons"] = ["risk-arbitrage expected edge is not positive after the single supplied cost"]
        return result
    return with_direction(result, state, direction, "observed event probability and payoff produce positive net expected edge")
