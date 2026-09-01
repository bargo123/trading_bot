"""Kalman residual/reversion perspective from an upstream fitted filter."""
from __future__ import annotations

from ._common import base, first, number, strings, values, with_direction

ALGORITHM_ID = "kalman_filter"
SOURCES = (
    "Statistical Arbitrage — Andrew Pole",
    "Quantitative Trading — Ernest Chan",
    "Machine Learning for Algorithmic Trading — Stefan Jansen",
)
KEYS = (
    "kalman_state", "kalman_residual", "kalman_zscore", "kalman_confirmation",
    "kalman_hedge_ratio", "kalman_observation_n", "kalman_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("kalman_residual",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    text = strings(state, "kalman_state", "kalman_confirmation")
    if any(token in text for token in ("failed", "unstable", "unconfirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["Kalman filter state is not stable or confirmed"]
        return result
    if "confirmed" not in text and any(token in text for token in ("oversold", "overbought", "reversion")):
        result["view"] = "WAIT"
        result["reasons"] = ["Kalman reversion state lacks explicit confirmation"]
        return result
    if any(token in text for token in ("oversold", "reversion_up", "buy")):
        return with_direction(result, state, "BUY", "confirmed Kalman residual reversion favors the upside")
    if any(token in text for token in ("overbought", "reversion_down", "sell")):
        return with_direction(result, state, "SELL", "confirmed Kalman residual reversion favors the downside")
    zscore = number(first(state, "kalman_zscore", "kalman_residual"))
    if zscore is not None and abs(zscore) >= 2:
        return with_direction(result, state, "BUY" if zscore < 0 else "SELL", "Kalman residual is materially displaced")
    result["view"] = "WAIT"
    result["reasons"] = ["Kalman residual is not a confirmed material displacement"]
    return result
