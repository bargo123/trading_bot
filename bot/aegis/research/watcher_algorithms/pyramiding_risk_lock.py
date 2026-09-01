"""Profit-funded pyramiding with a non-increasing risk envelope."""
from __future__ import annotations

from ._common import absent, base, first, number, explicitly_observed, normalized_status, values, with_direction

ALGORITHM_ID = "pyramiding_risk_lock"
SOURCES = ("Pyramiding — A Money Management Strategy To Increase Profits",)
KEYS = (
    "pyramid_add_preplanned",
    "pyramid_market_regime",
    "pyramid_same_thesis",
    "pyramid_position_profit_usd",
    "pyramid_risk_before_usd",
    "pyramid_risk_after_usd",
    "pyramid_max_risk_usd",
    "pyramid_add_direction",
    "pyramid_data_provenance",
)


def _truth(value):
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed"}


def _direction(value):
    direction = normalized_status(value).upper()
    return direction if direction in {"BUY", "SELL"} else None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("preplanned_profit_funded_risk_locked_add",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    preplanned = _truth(first(state, "pyramid_add_preplanned"))
    same_thesis = _truth(first(state, "pyramid_same_thesis"))
    regime = normalized_status(first(state, "pyramid_market_regime"))
    profit = number(first(state, "pyramid_position_profit_usd"))
    risk_before = number(first(state, "pyramid_risk_before_usd"))
    risk_after = number(first(state, "pyramid_risk_after_usd"))
    max_risk = number(first(state, "pyramid_max_risk_usd"))
    direction = _direction(first(state, "pyramid_add_direction"))
    provenance = first(state, "pyramid_data_provenance")
    missing = [
        key
        for key, value in (
            ("pyramid_add_preplanned", first(state, "pyramid_add_preplanned")),
            ("pyramid_market_regime", regime),
            ("pyramid_same_thesis", first(state, "pyramid_same_thesis")),
            ("pyramid_position_profit_usd", profit),
            ("pyramid_risk_before_usd", risk_before),
            ("pyramid_risk_after_usd", risk_after),
            ("pyramid_max_risk_usd", max_risk),
            ("pyramid_add_direction", direction),
        )
        if value is None or value == ""
    ]
    if missing or not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "journal")):
        if not explicitly_observed(provenance, accepted=("observed", "measured", "timestamped", "journal")):
            missing.append("pyramid_data_provenance")
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = list(dict.fromkeys(missing))
        return result

    result["pyramiding_risk_locked"] = False
    if not preplanned or not same_thesis or profit <= 0:
        result["pyramiding_assessment"] = "NOT_PROFIT_FUNDED"
        result["reasons"] = ["an add requires a preplanned same-thesis position that is already profitable"]
        return result
    if not any(token in regime for token in ("strong trend", "strong_trend", "trend")) or any(
        token in regime for token in ("range", "chop", "sideways")
    ):
        result["pyramiding_assessment"] = "REGIME_UNSUITABLE"
        result["reasons"] = ["pyramiding is restricted to an observed strong trend, not a range or choppy state"]
        return result
    if min(risk_before, risk_after, max_risk) < 0:
        result["pyramiding_assessment"] = "INVALID_RISK_INPUT"
        result["reasons"] = ["risk observations must be non-negative"]
        return result
    if risk_after > max_risk or risk_after > risk_before:
        result["pyramiding_assessment"] = "RISK_INCREASE"
        result["reasons"] = ["the add would exceed the declared maximum or increase risk after trailing stops"]
        return result

    result["pyramiding_risk_locked"] = True
    result["pyramiding_assessment"] = "SAFE_TREND_ADD"
    result["pyramiding_risk_after_usd"] = risk_after
    return with_direction(result, state, direction, "the planned profit-funded add leaves the declared risk envelope non-increasing")
