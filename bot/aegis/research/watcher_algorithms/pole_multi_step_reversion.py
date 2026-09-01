"""Andrew Pole's conditional multi-step reversion-probability perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, side, values, with_direction

ALGORITHM_ID = "pole_multi_step_reversion"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "side",
    "pole_current_value",
    "pole_local_median",
    "pole_one_step_reversion_probability",
    "pole_reversion_steps",
    "pole_independence_assumption",
    "pole_multistep_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_multistep_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("pole_multistep_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    current = number(first(state, "pole_current_value"))
    median = number(first(state, "pole_local_median"))
    probability = number(first(state, "pole_one_step_reversion_probability"))
    steps = number(first(state, "pole_reversion_steps"))
    if (
        candidate_side is None
        or current is None
        or median is None
        or probability is None
        or steps is None
        or not 0.0 <= probability <= 1.0
        or steps <= 0
        or int(steps) != steps
    ):
        result["pole_multistep_action"] = "INVALID_MULTISTEP_INPUT"
        result["reasons"] = ["multi-step reversion needs bounded probability and a positive integer horizon"]
        return result
    if not explicitly_validated(first(state, "pole_independence_assumption")):
        result["pole_multistep_action"] = "INDEPENDENCE_NOT_VALIDATED"
        result["reasons"] = ["the binomial multi-step extension requires an explicit independence observation"]
        return result

    at_least_one = 1.0 - (1.0 - probability) ** int(steps)
    result.update(
        {
            "pole_one_step_reversion_probability": probability,
            "pole_reversion_steps": int(steps),
            "pole_at_least_one_reversion_probability": at_least_one,
            "pole_multistep_action": "NO_POSITIVE_REVERSION_BIAS" if probability <= 0.5 else "REVERSION_BIAS",
        }
    )
    if probability <= 0.5:
        result["reasons"] = ["one-step reversion probability does not exceed the neutral bias"]
        return result
    if current == median:
        result["pole_multistep_action"] = "NO_DISPLACEMENT"
        result["reasons"] = ["current value is at the local median"]
        return result
    signal = "BUY" if current < median else "SELL"
    return with_direction(result, state, signal, "conditional multi-step reversion probability favors a move toward the local median")
