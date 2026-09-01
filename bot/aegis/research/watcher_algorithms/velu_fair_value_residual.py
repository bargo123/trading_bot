"""Velu, Hardy, and Nehren's factor-adjusted fair-value residual perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, explicitly_observed, first, number, side, values, with_direction

ALGORITHM_ID = "velu_fair_value_residual"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_observed_return",
    "velu_factor_expected_return",
    "velu_fair_value_residual_threshold",
    "velu_factor_model_status",
    "velu_fair_value_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_fair_value_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_fair_value_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    observed = number(first(state, "velu_observed_return"))
    expected = number(first(state, "velu_factor_expected_return"))
    threshold = number(first(state, "velu_fair_value_residual_threshold"))
    if candidate_side is None or observed is None or expected is None or threshold is None or threshold <= 0:
        result["velu_fair_value_action"] = "INVALID_FAIR_VALUE_INPUT"
        result["reasons"] = ["fair-value residual needs finite returns and a positive deviation threshold"]
        return result
    if not explicitly_validated(first(state, "velu_factor_model_status")):
        result["velu_fair_value_action"] = "FACTOR_MODEL_NOT_VALIDATED"
        result["reasons"] = ["factor-adjusted residual is not usable without a validated point-in-time model"]
        return result

    residual = observed - expected
    result.update(
        {
            "velu_factor_residual": residual,
            "velu_fair_value_residual_threshold": threshold,
        }
    )
    if abs(residual) <= threshold:
        result["velu_fair_value_action"] = "RESIDUAL_WITHIN_BAND"
        result["reasons"] = ["observed return is not materially displaced from factor-implied fair value"]
        return result
    result["velu_fair_value_action"] = "RESIDUAL_REVERSION"
    signal = "BUY" if residual < 0 else "SELL"
    return with_direction(result, state, signal, "material factor-unexplained residual favors reversion toward fair value")
