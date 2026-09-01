"""Chan's volatility-scaled opening-gap momentum perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "chan_opening_gap_momentum"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_gap_open_price",
    "chan_gap_prior_high",
    "chan_gap_prior_low",
    "chan_gap_reference_volatility",
    "chan_gap_entry_zscore",
    "chan_gap_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "chan_gap_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("chan_gap_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    open_price = number(first(state, "chan_gap_open_price"))
    prior_high = number(first(state, "chan_gap_prior_high"))
    prior_low = number(first(state, "chan_gap_prior_low"))
    volatility = number(first(state, "chan_gap_reference_volatility"))
    entry_zscore = number(first(state, "chan_gap_entry_zscore"))
    if any(value is None or value <= 0 for value in (open_price, prior_high, prior_low, volatility, entry_zscore)) or prior_high <= prior_low:
        result["chan_gap_assessment"] = "INVALID_GAP_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["opening gap prices, reference volatility, and entry z-score must be valid positive observations"]
        return result
    threshold = entry_zscore * volatility
    if threshold >= 1.0:
        result["chan_gap_assessment"] = "INVALID_GAP_THRESHOLD"
        result["view"] = "WAIT"
        result["reasons"] = ["the volatility-scaled downside threshold must remain above zero"]
        return result
    upper = prior_high * (1.0 + threshold)
    lower = prior_low * (1.0 - threshold)
    result["chan_gap_upper_trigger"] = upper
    result["chan_gap_lower_trigger"] = lower
    if open_price > upper:
        result["chan_gap_assessment"] = "UP_GAP_BREAK"
        return with_direction(result, state, "BUY", "the session open exceeded the prior high by the source volatility-scaled threshold")
    if open_price < lower:
        result["chan_gap_assessment"] = "DOWN_GAP_BREAK"
        return with_direction(result, state, "SELL", "the session open fell below the prior low by the source volatility-scaled threshold")
    result["chan_gap_assessment"] = "NO_QUALIFYING_GAP"
    result["view"] = "WAIT"
    result["reasons"] = ["the opening price did not clear either volatility-scaled prior-range boundary"]
    return result
