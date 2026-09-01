"""Velu, Hardy, and Nehren's sign/magnitude return-decomposition rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, number, side, values, with_direction

ALGORITHM_ID = "velu_sign_magnitude_decomposition"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_direction_probability",
    "velu_expected_absolute_move",
    "velu_transaction_cost",
    "velu_decomposition_assumption",
    "velu_decomposition_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_decomposition_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_decomposition_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    probability = number(first(state, "velu_direction_probability"))
    absolute_move = number(first(state, "velu_expected_absolute_move"))
    cost = number(first(state, "velu_transaction_cost"))
    if (
        candidate_side is None
        or probability is None
        or absolute_move is None
        or cost is None
        or not 0.0 <= probability <= 1.0
        or absolute_move < 0
        or cost < 0
    ):
        result["velu_decomposition_action"] = "INVALID_DECOMPOSITION_INPUT"
        result["reasons"] = ["decomposition needs bounded direction probability and nonnegative measured move/cost"]
        return result
    if not explicitly_validated(first(state, "velu_decomposition_assumption")):
        result["velu_decomposition_action"] = "ASSUMPTION_NOT_VALIDATED"
        result["reasons"] = ["the sign/magnitude combination requires a validated model assumption"]
        return result

    expected_signed_move = (2.0 * probability - 1.0) * absolute_move
    candidate_move = expected_signed_move if candidate_side == "BUY" else -expected_signed_move
    expected_net_move = candidate_move - cost
    result.update(
        {
            "velu_expected_signed_move": expected_signed_move,
            "velu_expected_net_move": expected_net_move,
            "velu_direction_probability": probability,
            "velu_expected_absolute_move": absolute_move,
            "velu_transaction_cost": cost,
        }
    )
    if expected_net_move <= 0:
        result["velu_decomposition_action"] = "COST_EXCEEDS_EXPECTED_MOVE"
        result["reasons"] = ["expected signed move does not clear the measured transaction-cost floor"]
        return result
    signal = "BUY" if expected_signed_move > 0 else "SELL" if expected_signed_move < 0 else None
    if signal != candidate_side:
        result["velu_decomposition_action"] = "SIDE_NOT_SUPPORTED_BY_FORECAST"
        result["reasons"] = ["candidate side is not the direction supported by the decomposed forecast"]
        return result
    if signal is None:
        result["velu_decomposition_action"] = "NO_DIRECTIONAL_EDGE"
        result["reasons"] = ["direction probability is neutral"]
        return result
    result["velu_decomposition_action"] = "POSITIVE_NET_EXCESS_MOVE"
    return with_direction(result, state, signal, "direction probability and expected magnitude imply positive net excess movement")
