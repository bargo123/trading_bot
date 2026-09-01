"""Gray--Vogel lottery-characteristic avoidance filter."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "gray_vogel_lottery_avoidance"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "side",
    "gray_lottery_max_return",
    "gray_lottery_beta",
    "gray_lottery_max_return_limit",
    "gray_lottery_beta_limit",
    "gray_lottery_lookback",
    "gray_lottery_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = first(state, "gray_lottery_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical")):
        missing.append("gray_lottery_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    max_return = number(first(state, "gray_lottery_max_return"))
    beta = number(first(state, "gray_lottery_beta"))
    max_limit = number(first(state, "gray_lottery_max_return_limit"))
    beta_limit = number(first(state, "gray_lottery_beta_limit"))
    lookback = normalized_status(first(state, "gray_lottery_lookback"))
    result["directional_claim"] = False
    if (
        any(value is None for value in (max_return, beta, max_limit, beta_limit))
        or max_limit <= 0
        or beta_limit <= 0
        or max_return < 0
        or beta < 0
        or lookback not in {"prior month", "previous month"}
    ):
        result["gray_lottery_assessment"] = "INVALID_LOTTERY_INPUT"
        result["reasons"] = ["lottery avoidance needs nonnegative observed MAX/beta, positive limits, and a prior-month window"]
        return result

    result.update(
        {
            "gray_lottery_max_return": max_return,
            "gray_lottery_beta": beta,
            "gray_lottery_max_return_limit": max_limit,
            "gray_lottery_beta_limit": beta_limit,
        }
    )
    elevated = max_return >= max_limit or beta >= beta_limit
    if elevated:
        result["gray_lottery_assessment"] = "AVOID_LOTTERY_EXPOSURE"
        result["reasons"] = ["the observed prior-month extreme return or beta exceeds the copied lottery-risk limit"]
        result["warnings"] = ["a high-momentum path may contain lottery-like jump risk and should not be treated as quality momentum"]
    else:
        result["gray_lottery_assessment"] = "LOTTERY_EXPOSURE_NOT_ELEVATED"
        result["reasons"] = ["the observed prior-month MAX and beta are below the supplied lottery-risk limits"]
    return result
