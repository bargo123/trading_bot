"""Ponsi's long-horizon interest-rate differential perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ponsi_interest_rate_edge"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "side",
    "ponsi_base_rate",
    "ponsi_quote_rate",
    "ponsi_rate_differential_bps",
    "ponsi_rate_differential_change_bps",
    "ponsi_rate_policy_outlook",
    "ponsi_rate_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "ponsi_rate_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("ponsi_rate_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    base_rate = number(first(state, "ponsi_base_rate"))
    quote_rate = number(first(state, "ponsi_quote_rate"))
    differential = number(first(state, "ponsi_rate_differential_bps"))
    change = number(first(state, "ponsi_rate_differential_change_bps"))
    outlook = normalized_status(first(state, "ponsi_rate_policy_outlook"))
    if any(value is None for value in (base_rate, quote_rate, differential, change)) or base_rate == quote_rate or differential == 0:
        result["ponsi_carry_assessment"] = "INVALID_DIFFERENTIAL"
        result["reasons"] = ["base/quote rates and a non-zero signed differential are required"]
        return result
    if outlook not in {"widening", "widen", "expanding", "increase", "increasing"}:
        result["ponsi_carry_assessment"] = "DIFFERENTIAL_OUTLOOK_NOT_WIDENING"
        result["reasons"] = ["the source seeks a differential expected to expand, not merely a currently positive yield gap"]
        return result
    if (differential > 0 and change <= 0) or (differential < 0 and change >= 0):
        result["ponsi_carry_assessment"] = "DIFFERENTIAL_NOT_EXPANDING"
        result["reasons"] = ["the signed differential change does not increase the yield advantage of the base currency"]
        return result
    signal = "BUY" if differential > 0 else "SELL"
    result["ponsi_carry_assessment"] = "WIDENING_CARRY_BIAS"
    result["ponsi_rate_differential_bps"] = differential
    result["directional_claim"] = True
    return with_direction(result, state, signal, "the observed base-versus-quote yield advantage is expected to widen")
