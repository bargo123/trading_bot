"""Regime-aware mean-reversion versus continuation algorithm."""
from __future__ import annotations
from ._common import base, first, number, side, strings, values, with_direction

ALGORITHM_ID = "mean_reversion_vs_momentum"
SOURCES = ("Ernest Chan — Quantitative Trading", "Adam Grimes — The Art and Science of Technical Analysis", "Jean-Philippe Bouchaud — Trades, Quotes and Prices", "Andrew Pole — Statistical Arbitrage")
KEYS = ("regime", "distance_from_mean", "zscore", "extension", "momentum", "trend")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("regime_and_distance",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, *KEYS)
    zscore = number(first(state, "zscore", "distance_from_mean", "extension"))
    if "range" in text and zscore is not None and abs(zscore) >= 2:
        return with_direction(result, state, "SELL" if zscore > 0 else "BUY", "range plus measured extension favors a mean-reversion test")
    if "trend" in text and "range" not in text:
        result["view"] = side(state) or "WAIT"
        result["reasons"] = ["trend regime favors continuation over an unproven countertrend fade"]
        return result
    result["view"] = "WAIT"
    result["reasons"] = ["mean-reversion versus momentum regime is not decisive"]
    return result
