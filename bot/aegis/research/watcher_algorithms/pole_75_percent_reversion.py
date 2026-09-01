"""Andrew Pole's conditional 75-percent local-reversion perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, side, values, with_direction

ALGORITHM_ID = "pole_75_percent_reversion"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "side",
    "pole_current_value",
    "pole_local_median",
    "pole_reversion_rate",
    "pole_min_reversion_rate",
    "pole_reversion_observation_n",
    "pole_reversion_assumptions",
    "pole_reversion_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_reversion_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("pole_reversion_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    current = number(first(state, "pole_current_value"))
    median = number(first(state, "pole_local_median"))
    rate = number(first(state, "pole_reversion_rate"))
    minimum_rate = number(first(state, "pole_min_reversion_rate"))
    observation_n = number(first(state, "pole_reversion_observation_n"))
    if (
        candidate_side is None
        or current is None
        or median is None
        or rate is None
        or minimum_rate is None
        or observation_n is None
        or not 0.0 <= rate <= 1.0
        or not 0.0 <= minimum_rate <= 1.0
        or observation_n <= 0
        or minimum_rate < 0.75
    ):
        result["pole_reversion_action"] = "INVALID_REVERSION_INPUT"
        result["reasons"] = ["conditional reversion needs bounded measured rates, sample size, and a 75% rule threshold"]
        return result
    if not explicitly_validated(first(state, "pole_reversion_assumptions")):
        result["pole_reversion_action"] = "ASSUMPTIONS_NOT_VALIDATED"
        result["reasons"] = ["the source rule is conditional on its reversion assumptions"]
        return result

    result.update(
        {
            "pole_reversion_rule": "75_PERCENT_CONDITIONAL",
            "pole_reversion_probability": rate,
            "pole_reversion_observation_n": observation_n,
            "pole_reversion_deviation": current - median,
            "pole_reversion_action": "RATE_BELOW_RULE" if rate < minimum_rate else "RATE_SUPPORTS_RULE",
        }
    )
    if rate < minimum_rate:
        result["reasons"] = ["measured local reversion rate is below the configured conditional rule rate"]
        return result
    if current == median:
        result["pole_reversion_action"] = "NO_DISPLACEMENT"
        result["reasons"] = ["current value is at the local median"]
        return result
    signal = "BUY" if current < median else "SELL"
    return with_direction(result, state, signal, "measured displacement and validated local reversion evidence favor the median")
