"""Ernest Chan's validated time-series momentum perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "chan_time_series_momentum"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_tsm_past_return",
    "chan_tsm_lookback_days",
    "chan_tsm_holding_days",
    "chan_tsm_timeframe",
    "chan_tsm_parameter_validation",
    "chan_tsm_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "chan_tsm_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("chan_tsm_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    lookback = number(first(state, "chan_tsm_lookback_days"))
    holding = number(first(state, "chan_tsm_holding_days"))
    past_return = number(first(state, "chan_tsm_past_return"))
    validation = normalized_status(first(state, "chan_tsm_parameter_validation"))
    if normalized_status(first(state, "chan_tsm_timeframe")) != "daily":
        result["view"] = "WAIT"
        result["reasons"] = ["the source time-series momentum rule is evaluated on daily data"]
        return result
    if any(value is None for value in (lookback, holding, past_return)) or lookback <= 0 or holding <= 0:
        result["view"] = "WAIT"
        result["reasons"] = ["lookback, holding period, and past return must be valid"]
        return result
    if validation not in {"chronological oos", "walk forward", "out of sample", "validated"}:
        result["view"] = "WAIT"
        result["reasons"] = ["lookback and holding parameters lack chronological out-of-sample validation"]
        return result
    signal = "BUY" if past_return > 0 else "SELL" if past_return < 0 else None
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["validated past return has no directional sign"]
        return result
    result["chan_tsm_daily_tranche_fraction"] = 1.0 / holding
    return with_direction(result, state, signal, "validated daily time-series return sign supplies the momentum direction")
