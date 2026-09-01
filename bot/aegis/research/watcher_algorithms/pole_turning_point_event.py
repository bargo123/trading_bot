"""Pole's volatility-qualified causal turning-point event rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction


ALGORITHM_ID = "pole_turning_point_event"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "side",
    "pole_turning_point_type",
    "pole_turning_point_extreme_price",
    "pole_turning_point_current_price",
    "pole_turning_point_annualized_volatility",
    "pole_turning_point_qualifying_fraction",
    "pole_turning_point_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_turning_point_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("pole_turning_point_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in values(state, *KEYS)])
    point_type = normalized_status(first(state, "pole_turning_point_type")).replace(" ", "_")
    extreme = number(first(state, "pole_turning_point_extreme_price"))
    current = number(first(state, "pole_turning_point_current_price"))
    volatility = number(first(state, "pole_turning_point_annualized_volatility"))
    fraction = number(first(state, "pole_turning_point_qualifying_fraction"))
    if point_type not in {"peak", "trough"}:
        result["pole_turning_point_action"] = "INVALID_POINT_TYPE"
        result["reasons"] = ["turning-point type must be an observed peak or trough"]
        return result
    if (
        extreme is None
        or current is None
        or volatility is None
        or fraction is None
        or extreme <= 0.0
        or volatility <= 0.0
        or fraction <= 0.0
    ):
        result["pole_turning_point_action"] = "INVALID_TURNING_POINT_INPUT"
        result["reasons"] = ["turning-point event needs positive price, volatility, and qualifying fraction inputs"]
        return result

    reversal_return = (current - extreme) / extreme
    threshold_return = -fraction * volatility if point_type == "peak" else fraction * volatility
    result.update(
        {
            "pole_turning_point_type": point_type,
            "pole_turning_point_reversal_return": reversal_return,
            "pole_turning_point_threshold_return": threshold_return,
            "pole_turning_point_confirmed": False,
        }
    )

    if point_type == "peak":
        qualified = current < extreme and reversal_return <= threshold_return
        signal = "SELL"
        action = "CONFIRMED_PEAK"
    else:
        qualified = current > extreme and reversal_return >= threshold_return
        signal = "BUY"
        action = "CONFIRMED_TROUGH"

    if not qualified:
        result["pole_turning_point_action"] = "WAIT_FOR_QUALIFYING_REVERSAL"
        result["reasons"] = ["the causal reversal has not reached the local-volatility qualification fraction"]
        return result

    result["pole_turning_point_action"] = action
    result["pole_turning_point_confirmed"] = True
    return with_direction(
        result,
        state,
        signal,
        "current price has reversed from the observed local extreme by the calibrated volatility fraction",
    )

