"""López de Prado probabilistic Sharpe-ratio diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import finite_series, moments, provenance_ok, psr

ALGORITHM_ID = "deprado_probabilistic_sharpe"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_excess_returns",
    "deprado_target_sharpe",
    "deprado_returns_data_provenance",
)


def evaluate(state):
    returns = finite_series(state, "deprado_excess_returns")
    target = number(first(state, "deprado_target_sharpe"))
    found = values(state, *KEYS)
    missing = []
    if returns is None or len(returns) < 3:
        missing.append("deprado_excess_returns")
    if target is None:
        missing.append("deprado_target_sharpe")
    provenance = first(state, "deprado_returns_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_returns_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    statistics = moments(returns)
    if statistics is None:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["returns must contain at least three observations with non-zero variance"]
        return result
    mean, standard_deviation, skewness, kurtosis = statistics
    observed_sharpe = mean / standard_deviation
    probability = psr(observed_sharpe, target, len(returns), skewness, kurtosis)
    if probability is None:
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["PSR correction denominator is not positive"]
        return result

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "post_outcome_validation"
    result["deprado_observed_sharpe"] = observed_sharpe
    result["deprado_probabilistic_sharpe"] = probability
    result["deprado_psr_target_sharpe"] = target
    result["deprado_psr_sample_n"] = len(returns)
    result["deprado_psr_skewness"] = skewness
    result["deprado_psr_kurtosis"] = kurtosis
    result["deprado_psr_assessment"] = (
        "PROBABILITY_SHARPE_ABOVE_TARGET" if probability >= 0.5 else "PROBABILITY_SHARPE_NOT_ABOVE_TARGET"
    )
    result["warnings"] = ["PSR is an outcome diagnostic, not an entry threshold"]
    return result
