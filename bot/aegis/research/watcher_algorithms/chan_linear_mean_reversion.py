"""Ernest Chan's linear time-series mean-reversion perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "chan_linear_mean_reversion"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_linear_zscore",
    "chan_linear_entry_zscore",
    "chan_linear_half_life",
    "chan_linear_horizon",
    "chan_linear_stationarity",
    "chan_linear_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "chan_linear_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("chan_linear_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not explicitly_validated(first(state, "chan_linear_stationarity")):
        result["view"] = "WAIT"
        result["reasons"] = ["the price series has no explicit stationary/validated status"]
        return result
    zscore = number(first(state, "chan_linear_zscore"))
    threshold = number(first(state, "chan_linear_entry_zscore"))
    half_life = number(first(state, "chan_linear_half_life"))
    horizon = number(first(state, "chan_linear_horizon"))
    if any(value is None for value in (zscore, threshold, half_life, horizon)) or threshold <= 0 or half_life <= 0 or horizon <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["z-score, entry threshold, half-life, and horizon must be valid positive observations"]
        return result
    if horizon > half_life:
        result["view"] = "WAIT"
        result["reasons"] = ["the trading horizon exceeds the observed mean-reversion half-life"]
        return result
    signal = "BUY" if zscore <= -threshold else "SELL" if zscore >= threshold else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["normalized deviation is inside the linear mean-reversion entry band"]
        return result
    result["chan_linear_position_signal"] = -zscore
    return with_direction(result, state, signal, "the validated series is beyond its moving-mean entry deviation")
