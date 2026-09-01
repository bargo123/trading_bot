"""The Ultimate Forex Trading System's causal correlation-lag perspective."""
from __future__ import annotations

import math

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_correlation_lag"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_corr_coefficient",
    "ultimate_corr_window_hours",
    "ultimate_leading_return",
    "ultimate_lagging_return",
    "ultimate_min_lag_gap",
    "ultimate_lagging_setup_confirmed",
    "ultimate_lagging_setup_direction",
    "ultimate_hours_since_divergence",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    corr = number(first(state, "ultimate_corr_coefficient"))
    periods = number(first(state, "ultimate_corr_window_hours"))
    leading = number(first(state, "ultimate_leading_return"))
    lagging = number(first(state, "ultimate_lagging_return"))
    minimum_gap = number(first(state, "ultimate_min_lag_gap"))
    hours = number(first(state, "ultimate_hours_since_divergence"))
    if any(value is None for value in (corr, periods, leading, lagging, minimum_gap, hours)):
        result["view"] = "WAIT"
        result["reasons"] = ["correlation and lag observations must be finite numbers"]
        return result
    if not (0.75 <= abs(corr) <= 0.85) or periods < 1:
        result["view"] = "WAIT"
        result["reasons"] = ["the observed 1H correlation is outside the source's 0.75-0.85 band"]
        return result
    if not _truthy(first(state, "ultimate_lagging_setup_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the lagging pair has no confirmed directional setup"]
        return result
    if hours < 0 or hours > 3:
        result["view"] = "WAIT"
        result["reasons"] = ["the correlation divergence is older than the source's three-hour window"]
        return result
    expected = math.copysign(abs(leading), corr)
    gap = expected - lagging
    if abs(expected) == 0 or minimum_gap <= 0 or abs(gap) < minimum_gap:
        result["view"] = "WAIT"
        result["reasons"] = ["the measured leader/lagger gap is not large enough"]
        return result
    signal = "BUY" if expected > 0 else "SELL"
    observed_setup = normalized_status(first(state, "ultimate_lagging_setup_direction")).upper()
    if observed_setup != signal:
        result["view"] = "WAIT"
        result["reasons"] = ["the confirmed lagging-pair setup disagrees with the correlation-implied direction"]
        return result
    result["ultimate_expected_lagging_return"] = expected
    result["ultimate_lag_gap"] = gap
    result["ultimate_only_trade_lagging_pair"] = True
    return with_direction(result, state, signal, "the causal leader/lagger divergence and lagging setup agree")
