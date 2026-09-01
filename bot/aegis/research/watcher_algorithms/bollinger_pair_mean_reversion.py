"""Chan-style Bollinger mean reversion on a validated stationary pair spread."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, number, strings, values, with_direction

ALGORITHM_ID = "bollinger_pair_mean_reversion"
SOURCES = (
    "Ernest Chan — Quantitative Trading",
    "Ernest Chan — Algorithmic Trading (Winning Strategies and Their Rationale)",
)
KEYS = (
    "pair", "pair_stationarity", "pair_zscore", "pair_signal",
    "bollinger_entry_zscore", "bollinger_exit_zscore",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("validated_pair_spread",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    stationarity = strings(state, "pair_stationarity", "cointegration")
    if not explicitly_validated(stationarity, accepted=("validated", "stationary")):
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "WAIT"
        result["reasons"] = ["pair spread is not explicitly validated as stationary or cointegrated"]
        return result
    zscore = number(first(state, "pair_zscore", "spread_zscore"))
    signal = str(first(state, "pair_signal") or "").strip().upper()
    if zscore is None or signal not in {"BUY", "SELL"}:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["pair_zscore_and_pair_signal"]
        return result
    entry_zscore = number(first(state, "bollinger_entry_zscore"))
    exit_zscore = number(first(state, "bollinger_exit_zscore"))
    entry_zscore = 1.0 if entry_zscore is None else entry_zscore
    exit_zscore = 0.0 if exit_zscore is None else exit_zscore
    if entry_zscore <= exit_zscore or entry_zscore <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["Bollinger entry and exit thresholds are invalid"]
        return result
    result["rule_parameters"] = {"entry_zscore": entry_zscore, "exit_zscore": exit_zscore}
    if abs(zscore) < entry_zscore:
        result["view"] = "WAIT"
        result["reasons"] = ["validated pair spread has not reached the Bollinger entry threshold"]
        return result
    return with_direction(result, state, signal, "validated pair spread reached the Chan-style Bollinger entry threshold")
