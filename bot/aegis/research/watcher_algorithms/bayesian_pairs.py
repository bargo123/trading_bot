"""Bayesian rolling-regression pair-spread perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, strings, values, with_direction

ALGORITHM_ID = "bayesian_pairs"
SOURCES = ("Stefan Jansen — Machine Learning for Algorithmic Trading", "Andrew Pole — Statistical Arbitrage")
KEYS = ("pair", "bayesian_pair_status", "bayesian_spread_zscore", "bayesian_pair_signal", "bayesian_posterior_uncertainty")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_bayesian_pair_spread",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    status = strings(state, "bayesian_pair_status")
    zscore = number(first(state, "bayesian_spread_zscore"))
    uncertainty = number(first(state, "bayesian_posterior_uncertainty"))
    signal = str(first(state, "bayesian_pair_signal") or "").strip().upper()
    if not explicitly_validated(status) or zscore is None or uncertainty is None or signal not in {"BUY", "SELL"}:
        result["view"] = "WAIT"
        result["reasons"] = ["Bayesian pair requires validated posterior spread evidence"]
        return result
    if uncertainty < 0 or abs(zscore) < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["posterior spread deviation is insufficient or uncertain"]
        return result
    return with_direction(result, state, signal, "validated Bayesian pair posterior supports the recorded reversion direction")
