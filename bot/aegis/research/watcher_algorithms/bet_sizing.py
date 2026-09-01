"""Probability/payoff bet-sizing context with an explicit cap."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, values

ALGORITHM_ID = "bet_sizing"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning", "Robert Carver — Systematic Trading")
KEYS = ("bet_probability", "bet_payoff_ratio", "bet_sizing_cap", "bet_sizing_status")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("capped_validated_bet_size",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    probability = number(first(state, "bet_probability"))
    payoff = number(first(state, "bet_payoff_ratio"))
    cap = number(first(state, "bet_sizing_cap"))
    if None in {probability, payoff, cap} or not 0 <= probability <= 1 or payoff <= 0 or cap <= 0 or not explicitly_validated(first(state, "bet_sizing_status")):
        result["view"] = "WAIT"
        result["reasons"] = ["bet sizing requires bounded probability, payoff, and validated cap"]
        return result
    edge = probability - (1 - probability) / payoff
    result["uncapped_edge_fraction"] = edge
    result["capped_fraction"] = max(0.0, min(cap, cap * max(0.0, edge)))
    result["view"] = "WAIT"
    result["reasons"] = ["bet sizing reports a capped allocation fraction and does not authorize a trade"]
    return result
