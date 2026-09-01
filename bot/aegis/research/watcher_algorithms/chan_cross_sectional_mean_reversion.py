"""Ernest Chan's linear cross-sectional long-short perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "chan_cross_sectional_mean_reversion"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_cross_sectional_relative_return",
    "chan_cross_sectional_universe_mean",
    "chan_cross_sectional_normalization",
    "chan_cross_sectional_universe_n",
    "chan_cross_sectional_rank_ready",
    "chan_cross_sectional_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "chan_cross_sectional_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("chan_cross_sectional_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "chan_cross_sectional_rank_ready")):
        result["view"] = "WAIT"
        result["reasons"] = ["the causal universe rank is not ready"]
        return result
    relative_return = number(first(state, "chan_cross_sectional_relative_return"))
    universe_mean = number(first(state, "chan_cross_sectional_universe_mean"))
    normalization = number(first(state, "chan_cross_sectional_normalization"))
    universe_n = number(first(state, "chan_cross_sectional_universe_n"))
    if any(value is None for value in (relative_return, universe_mean, normalization, universe_n)) or normalization <= 0 or universe_n < 3:
        result["view"] = "WAIT"
        result["reasons"] = ["relative return, universe mean, normalization, and universe size must be valid"]
        return result
    deviation = relative_return - universe_mean
    if deviation == 0:
        result["view"] = "WAIT"
        result["reasons"] = ["instrument return equals the causal universe mean"]
        return result
    signal = "BUY" if deviation < 0 else "SELL"
    result["chan_cross_sectional_weight"] = -deviation / normalization
    result["chan_cross_sectional_gross_capital"] = 1.0
    return with_direction(result, state, signal, "relative underperformance/overperformance supplies the linear long-short signal")
