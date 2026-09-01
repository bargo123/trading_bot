"""Pair-trading perspective requiring validated cointegration evidence."""
from __future__ import annotations

from ._common import base, explicitly_validated, first, number, strings, values, with_direction

ALGORITHM_ID = "cointegration_pairs"
SOURCES = (
    "Statistical Arbitrage — Andrew Pole",
    "Quantitative Trading — Ernest Chan",
    "Machine Trading — Ernest P. Chan",
)
KEYS = ("pair", "cointegration", "stationarity", "spread_zscore", "pair_signal", "hedge_ratio")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("pair_and_cointegration",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    validation = strings(state, "cointegration", "stationarity")
    if not explicitly_validated(validation) or any(token in validation for token in ("proxy", "not_validated", "not_estimated", "unstable", "false", "failed")):
        result["view"] = "WAIT"
        result["reasons"] = ["cointegration is absent or only a quote-return proxy"]
        return result
    zscore = number(first(state, "spread_zscore"))
    signal_text = strings(state, "pair_signal")
    if "buy" in signal_text:
        return with_direction(result, state, "BUY", "validated pair spread signal requests the first leg buy")
    if "sell" in signal_text:
        return with_direction(result, state, "SELL", "validated pair spread signal requests the first leg sell")
    if zscore is None:
        result["view"] = "WAIT"
        result["reasons"] = ["validated pair relationship lacks a numeric spread deviation"]
    elif zscore <= -2:
        return with_direction(result, state, "BUY", "validated pair spread is sufficiently below its mean")
    elif zscore >= 2:
        return with_direction(result, state, "SELL", "validated pair spread is sufficiently above its mean")
    else:
        result["view"] = "WAIT"
        result["reasons"] = ["validated spread deviation is below the research trigger"]
    return result
