"""López de Prado strategy-failure probability diagnostic."""
from __future__ import annotations

import math
import random

from ._common import absent, base, explicitly_observed, first, number, values
from ._deprado_common import finite_series, provenance_ok

ALGORITHM_ID = "deprado_strategy_failure_probability"
SOURCES = ("Marcos López de Prado — Advances in Financial Machine Learning",)
KEYS = (
    "deprado_bet_returns",
    "deprado_stop_loss",
    "deprado_profit_taking",
    "deprado_target_sharpe",
    "deprado_bets_per_year",
    "deprado_assessment_years",
    "deprado_bootstrap_iterations",
    "deprado_bootstrap_seed",
    "deprado_returns_data_provenance",
)


def _binary_sharpe(stop_loss: float, profit_taking: float, precision: float, frequency: float) -> float:
    mean = precision * profit_taking + (1.0 - precision) * stop_loss
    variance = precision * (1.0 - precision) * (profit_taking - stop_loss) ** 2
    if variance <= 0:
        return math.inf if mean > 0 else -math.inf
    return mean / math.sqrt(variance) * math.sqrt(frequency)


def _precision_threshold(stop_loss: float, profit_taking: float, target_sharpe: float, frequency: float) -> float:
    break_even = -stop_loss / (profit_taking - stop_loss)
    low = min(max(break_even, 0.0), 1.0 - 1e-9)
    high = 1.0 - 1e-9
    if _binary_sharpe(stop_loss, profit_taking, high, frequency) <= target_sharpe:
        return 1.0
    for _ in range(80):
        midpoint = (low + high) / 2.0
        if _binary_sharpe(stop_loss, profit_taking, midpoint, frequency) <= target_sharpe:
            low = midpoint
        else:
            high = midpoint
    return high


def evaluate(state):
    returns = finite_series(state, "deprado_bet_returns")
    stop_loss = number(first(state, "deprado_stop_loss"))
    profit_taking = number(first(state, "deprado_profit_taking"))
    target_sharpe = number(first(state, "deprado_target_sharpe"))
    bets_per_year = number(first(state, "deprado_bets_per_year"))
    years = number(first(state, "deprado_assessment_years"))
    iterations = number(first(state, "deprado_bootstrap_iterations"))
    seed = number(first(state, "deprado_bootstrap_seed"))
    found = values(state, *KEYS)
    missing = []
    if returns is None or not returns:
        missing.append("deprado_bet_returns")
    for key, value in (
        ("deprado_stop_loss", stop_loss),
        ("deprado_profit_taking", profit_taking),
        ("deprado_target_sharpe", target_sharpe),
        ("deprado_bets_per_year", bets_per_year),
        ("deprado_assessment_years", years),
        ("deprado_bootstrap_iterations", iterations),
        ("deprado_bootstrap_seed", seed),
    ):
        if value is None:
            missing.append(key)
    provenance = first(state, "deprado_returns_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("deprado_returns_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    if (
        stop_loss >= 0
        or profit_taking <= 0
        or bets_per_year <= 0
        or years <= 0
        or not iterations.is_integer()
        or iterations < 1
        or not seed.is_integer()
    ):
        result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="MISSING_DATA")
        result["reasons"] = ["failure model requires negative stop, positive target, and positive finite controls"]
        return result

    frequency = bets_per_year * years
    bootstrap_size = max(1, int(math.floor(frequency)))
    threshold = _precision_threshold(stop_loss, profit_taking, target_sharpe, frequency)
    rng = random.Random(int(seed))
    failures = 0
    for _ in range(int(iterations)):
        sample = rng.choices(returns, k=bootstrap_size)
        precision = sum(value > 0 for value in sample) / bootstrap_size
        failures += precision < threshold

    probability = failures / iterations
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["analysis_stage"] = "post_outcome_validation"
    result["deprado_empirical_precision"] = sum(value > 0 for value in returns) / len(returns)
    result["deprado_precision_threshold"] = threshold
    result["deprado_bootstrap_sample_n"] = bootstrap_size
    result["deprado_strategy_failure_probability"] = probability
    result["deprado_strategy_failure_assessment"] = (
        "HIGH_STRATEGY_FAILURE_RISK" if probability > 0.05 else "STRATEGY_FAILURE_RISK_ACCEPTABLE"
    )
    result["warnings"] = ["strategy failure risk is a research diagnostic, not an execution gate"]
    return result
