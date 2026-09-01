"""Grinold and Kahn's volatility, skill, and score alpha scaling rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction

ALGORITHM_ID = "grinold_alpha_scaling"
SOURCES = ("Richard Grinold, Ronald Kahn — Active Portfolio Management",)
KEYS = (
    "side",
    "grinold_residual_volatility",
    "grinold_information_coefficient",
    "grinold_standardized_score",
    "grinold_alpha_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "grinold_alpha_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("grinold_alpha_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    volatility = number(first(state, "grinold_residual_volatility"))
    ic = number(first(state, "grinold_information_coefficient"))
    score = number(first(state, "grinold_standardized_score"))
    if volatility is None or ic is None or score is None or volatility < 0.0 or not -1.0 <= ic <= 1.0:
        result["grinold_alpha_action"] = "INVALID_ALPHA_INPUT"
        result["reasons"] = [
            "residual volatility must be nonnegative and information coefficient must be bounded"
        ]
        return result

    alpha = volatility * ic * score
    result.update({
        "grinold_expected_alpha": alpha,
        "grinold_residual_volatility": volatility,
        "grinold_information_coefficient": ic,
        "grinold_standardized_score": score,
        "directional_claim": True,
    })
    if alpha > 0.0:
        result["grinold_alpha_action"] = "POSITIVE_EXPECTED_ALPHA"
        return with_direction(result, state, "BUY", "volatility-scaled skill and score imply positive residual alpha")
    if alpha < 0.0:
        result["grinold_alpha_action"] = "NEGATIVE_EXPECTED_ALPHA"
        return with_direction(result, state, "SELL", "volatility-scaled skill and score imply negative residual alpha")
    result["grinold_alpha_action"] = "ZERO_EXPECTED_ALPHA"
    result["reasons"] = ["the volatility-scaled skill score is zero"]
    return result
