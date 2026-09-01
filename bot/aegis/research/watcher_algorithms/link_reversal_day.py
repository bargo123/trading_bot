"""Marcel Link's reversal-day and key-reversal-day checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "link_reversal_day"
SOURCES = ("Marcel Link — High Probability Trading",)
KEYS = (
    "link_prior_trend",
    "link_reversal_type",
    "link_low_vs_prior_low",
    "link_close_vs_prior_close",
    "link_high_vs_prior_high",
    "link_stochastic_state",
    "link_volume_confirmed",
    "link_data_provenance",
)


def _ok(value) -> bool:
    text = normalized_status(value)
    return bool(text) and not any(token in text for token in ("synthetic", "fixture", "unknown", "unavailable"))


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _ok(first(state, "link_data_provenance")):
        missing.append("link_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    prior = normalized_status(first(state, "link_prior_trend"))
    reversal_type = normalized_status(first(state, "link_reversal_type"))
    low = number(first(state, "link_low_vs_prior_low"))
    close = number(first(state, "link_close_vs_prior_close"))
    high = number(first(state, "link_high_vs_prior_high"))
    stochastic = normalized_status(first(state, "link_stochastic_state"))
    if any(value is None for value in (low, close, high)) or first(state, "link_volume_confirmed") is not True:
        result["reasons"] = ["reversal geometry and above-normal volume must be observed"]
        return result
    signal = None
    if candidate_side == "BUY" and prior == "down" and low < 0 and close > 0 and stochastic == "oversold":
        if reversal_type != "key" or high > 0:
            signal = "BUY"
    elif candidate_side == "SELL" and prior == "up" and high > 0 and close < 0 and stochastic == "overbought":
        if reversal_type != "key" or low < 0:
            signal = "SELL"
    if signal is None:
        result["reasons"] = ["the reversal day, stochastic extreme, and prior trend do not align"]
        return result
    return with_direction(result, state, signal, "reversal-day close and volume confirm a possible trend change")
