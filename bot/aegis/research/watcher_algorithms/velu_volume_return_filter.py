"""Velu, Hardy, and Nehren's volume-conditioned return perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "velu_volume_return_filter"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_lagged_return",
    "velu_volume_turnover_change",
    "velu_return_volume_regime",
    "velu_return_volume_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_return_volume_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_return_volume_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    lagged_return = number(first(state, "velu_lagged_return"))
    turnover_change = number(first(state, "velu_volume_turnover_change"))
    regime = normalized_status(first(state, "velu_return_volume_regime"))
    if lagged_return is None or turnover_change is None or regime not in {"speculative", "liquidity"}:
        result["velu_return_volume_action"] = "INVALID_RETURN_VOLUME_INPUT"
        result["missing_inputs"] = ["valid measured return-volume regime"]
        result["view"] = "MISSING_DATA"
        result["reasons"] = [
            "the volume-return filter needs an explicit speculative or liquidity regime"
        ]
        return result
    if lagged_return == 0:
        result["velu_return_volume_action"] = "NO_DIRECTIONAL_RETURN"
        result["reasons"] = ["the measured lagged return has no directional information"]
        return result

    continuation_direction = "BUY" if lagged_return > 0 else "SELL"
    if turnover_change > 0 and regime == "liquidity":
        signal = "SELL" if continuation_direction == "BUY" else "BUY"
        action = "HIGH_ACTIVITY_REVERSAL"
        reason = "high activity in the liquidity regime favors reversal of the lagged return"
    elif turnover_change > 0 and regime == "speculative":
        signal = continuation_direction
        action = "HIGH_ACTIVITY_CONTINUATION"
        reason = "high activity in the speculative regime favors continuation of the lagged return"
    else:
        signal = continuation_direction
        action = "LOW_ACTIVITY_CONTINUATION"
        reason = "low or falling activity is paired with the observed return-continuation perspective"
    result.update(
        {
            "velu_lagged_return": lagged_return,
            "velu_volume_turnover_change": turnover_change,
            "velu_return_volume_regime": regime,
            "velu_return_volume_action": action,
        }
    )
    return with_direction(result, state, signal, reason)
