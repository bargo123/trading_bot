"""Measured pair-spread, stationarity, and reversion algorithm."""
from __future__ import annotations
from ._common import base, explicitly_validated, first, number, values, with_direction

ALGORITHM_ID = "statistical_arbitrage"
SOURCES = ("Andrew Pole — Statistical Arbitrage", "Ernest Chan — Quantitative Trading", "Ernest Chan — Machine Trading", "Rishi Narang — Inside the Black Box")
KEYS = ("pair", "spread", "spread_zscore", "residual", "cointegration", "stationarity", "hedge_ratio", "relative_value")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("pair_spread_and_stationarity",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    zscore = number(first(state, "spread_zscore", "residual"))
    if zscore is None:
        result["view"] = "WAIT"
        result["reasons"] = ["pair relationship is present but no measured spread deviation is recorded"]
        return result
    stationarity = first(state, "cointegration", "stationarity")
    stationarity_text = str(stationarity or "").lower()
    if not explicitly_validated(stationarity) or any(token in stationarity_text for token in ("proxy", "not_estimated", "not_validated", "unvalidated")):
        result["view"] = "WAIT"
        result["reasons"] = ["quote-return pair context is provisional; stationarity is not validated"]
        result["warnings"] = ["a correlation or price-profile proxy cannot establish a tradable statistical-arbitrage relationship"]
        return result
    if any(token in stationarity_text for token in ("false", "unstable", "no", "fail")):
        result["view"] = "WAIT"
        result["reasons"] = ["stationarity/cointegration support is explicitly absent"]
        return result
    if abs(zscore) < 2:
        result["view"] = "WAIT"
        result["reasons"] = ["spread deviation is below the recorded research trigger"]
        return result
    return with_direction(result, state, "SELL" if zscore > 0 else "BUY", "measured spread deviation favors reversion")
