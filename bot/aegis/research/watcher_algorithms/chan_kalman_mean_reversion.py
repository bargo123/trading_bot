"""Ernest Chan's dynamic-beta Kalman spread mean-reversion perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "chan_kalman_mean_reversion"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_kalman_pair",
    "chan_kalman_error",
    "chan_kalman_predicted_std",
    "chan_kalman_entry_sigma",
    "chan_kalman_beta",
    "chan_kalman_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "chan_kalman_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("chan_kalman_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    error = number(first(state, "chan_kalman_error"))
    predicted_std = number(first(state, "chan_kalman_predicted_std"))
    entry_sigma = number(first(state, "chan_kalman_entry_sigma"))
    beta = number(first(state, "chan_kalman_beta"))
    if any(value is None for value in (error, predicted_std, entry_sigma, beta)) or predicted_std <= 0 or entry_sigma <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["Kalman error, predicted deviation, entry sigma, and beta must be valid"]
        return result
    band = entry_sigma * predicted_std
    signal = "BUY" if error <= -band else "SELL" if error >= band else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["Kalman measurement error is inside the predicted deviation band"]
        return result
    result["chan_kalman_entry_band"] = band
    return with_direction(result, state, signal, "dynamic-beta spread error has crossed the source deviation threshold")
