"""López de Prado deflated Sharpe-ratio diagnostic."""
from __future__ import annotations

import math
from statistics import NormalDist

from ._common import absent, base, explicitly_observed, first, values
from ._deprado_common import finite_series, moments, provenance_ok, psr

ALGORITHM_ID = "deprado_deflated_sharpe"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_selected_excess_returns",
    "deprado_trial_sharpes",
    "deprado_returns_data_provenance",
    "deprado_trial_data_provenance",
)


def evaluate(state):
    selected_returns = finite_series(state, "deprado_selected_excess_returns")
    trial_sharpes = finite_series(state, "deprado_trial_sharpes")
    found = values(state, *KEYS)
    missing = []
    if selected_returns is None or len(selected_returns) < 3:
        missing.append("deprado_selected_excess_returns")
    if trial_sharpes is None or len(trial_sharpes) < 2:
        missing.append("deprado_trial_sharpes")
    for key in ("deprado_returns_data_provenance", "deprado_trial_data_provenance"):
        provenance = first(state, key)
        if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
            missing.append(key)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    selected_moments = moments(selected_returns)
    if selected_moments is None:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["selected returns must have non-zero variance"]
        return result
    mean, standard_deviation, skewness, kurtosis = selected_moments
    observed_sharpe = mean / standard_deviation
    trial_variance = sum((value - sum(trial_sharpes) / len(trial_sharpes)) ** 2 for value in trial_sharpes) / len(trial_sharpes)
    trial_count = len(trial_sharpes)
    gamma = 0.5772156649015329
    benchmark = math.sqrt(trial_variance) * (
        (1.0 - gamma) * NormalDist().inv_cdf(1.0 - 1.0 / trial_count)
        + gamma * NormalDist().inv_cdf(1.0 - 1.0 / (trial_count * math.e))
    )
    probability = psr(observed_sharpe, benchmark, len(selected_returns), skewness, kurtosis)
    if probability is None:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["DSR correction denominator is not positive"]
        return result

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "post_outcome_validation"
    result["deprado_observed_sharpe"] = observed_sharpe
    result["deprado_expected_max_sharpe"] = benchmark
    result["deprado_deflated_sharpe"] = probability
    result["deprado_trial_count"] = trial_count
    result["deprado_dsr_assessment"] = (
        "SELECTION_ADJUSTED_SUPPORT" if probability >= 0.95 else "SELECTION_ADJUSTED_NOT_SUPPORTED"
    )
    result["warnings"] = ["DSR adjusts research evidence for multiple testing; it is not a trade gate"]
    return result
