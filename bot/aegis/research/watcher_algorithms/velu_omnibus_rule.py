"""Velu, Hardy, and Nehren's price/volatility/volume omnibus rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "velu_omnibus_rule"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_price_rule_direction",
    "velu_realized_volatility",
    "velu_predicted_volatility",
    "velu_cumulative_actual_volume",
    "velu_cumulative_predicted_volume",
    "velu_omnibus_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_omnibus_data_provenance"),
        accepted=("observed", "measured"),
    ):
        missing.append("velu_omnibus_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    price_direction = normalized_status(first(state, "velu_price_rule_direction"))
    realized = number(first(state, "velu_realized_volatility"))
    predicted = number(first(state, "velu_predicted_volatility"))
    actual_volume = number(first(state, "velu_cumulative_actual_volume"))
    predicted_volume = number(first(state, "velu_cumulative_predicted_volume"))
    if (
        candidate_side is None
        or price_direction not in {"up", "down"}
        or any(value is None for value in (realized, predicted, actual_volume, predicted_volume))
        or realized < 0
        or predicted <= 0
        or actual_volume < 0
        or predicted_volume <= 0
    ):
        result["velu_omnibus_action"] = "INVALID_OMNIBUS_INPUT"
        result["reasons"] = ["omnibus rule needs explicit side, direction, and nonnegative measured volume/volatility"]
        return result

    price_favors = (candidate_side == "BUY" and price_direction == "up") or (
        candidate_side == "SELL" and price_direction == "down"
    )
    result.update(
        {
            "velu_price_rule_direction": price_direction.upper(),
            "velu_realized_volatility": realized,
            "velu_predicted_volatility": predicted,
            "velu_cumulative_actual_volume": actual_volume,
            "velu_cumulative_predicted_volume": predicted_volume,
            "velu_omnibus_exit_if_any_condition_fails": True,
        }
    )
    if not price_favors:
        result["velu_omnibus_action"] = "PRICE_RULE_NOT_FAVORABLE"
        result["reasons"] = ["the price-based rule does not favor the candidate side"]
        return result
    if realized >= predicted:
        result["velu_omnibus_action"] = "REALIZED_VOL_NOT_BELOW_FORECAST"
        result["reasons"] = ["realized volatility is not below the point-in-time forecast"]
        return result
    if actual_volume >= predicted_volume:
        result["velu_omnibus_action"] = "ACTUAL_VOLUME_NOT_BELOW_FORECAST"
        result["reasons"] = ["cumulative actual volume is not below the point-in-time forecast"]
        return result
    result["velu_omnibus_action"] = "ENTRY_ALL_CONDITIONS_TRUE"
    return with_direction(result, state, candidate_side, "price rule, lower realized volatility, and lower cumulative volume all agree")
