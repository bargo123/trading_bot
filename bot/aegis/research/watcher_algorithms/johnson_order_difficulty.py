"""Order-difficulty diagnostic from Johnson's optimal-trading chapter."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, side, values

ALGORITHM_ID = "johnson_order_difficulty"
SOURCES = ("Barry Johnson — Algorithmic Trading and DMA",)
KEYS = (
    "side",
    "johnson_order_size_to_adv",
    "johnson_liquidity_state",
    "johnson_volatility_state",
    "johnson_price_momentum_direction",
    "johnson_urgency",
    "johnson_horizon_s",
    "johnson_difficulty_data_provenance",
)


def _label(value):
    return normalized_status(value)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("size_liquidity_volatility_momentum_urgency",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    size_to_adv = number(first(state, "johnson_order_size_to_adv"))
    liquidity = _label(first(state, "johnson_liquidity_state"))
    volatility = _label(first(state, "johnson_volatility_state"))
    momentum = _label(first(state, "johnson_price_momentum_direction"))
    urgency = _label(first(state, "johnson_urgency"))
    horizon = number(first(state, "johnson_horizon_s"))
    missing = [
        key for key, value in (
            ("side", candidate_side),
            ("johnson_order_size_to_adv", size_to_adv),
            ("johnson_liquidity_state", liquidity),
            ("johnson_volatility_state", volatility),
            ("johnson_price_momentum_direction", momentum),
            ("johnson_urgency", urgency),
            ("johnson_horizon_s", horizon),
        ) if value is None
    ]
    if missing:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = missing
        return result
    if size_to_adv < 0 or horizon <= 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["order size share and horizon must be non-negative/positive"]
        return result
    if not explicitly_observed(first(state, "johnson_difficulty_data_provenance"), accepted=("observed", "measured")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["johnson_difficulty_data_provenance"]
        result["reasons"] = ["order-difficulty inputs lack observed TCA provenance"]
        return result

    if any(token in liquidity for token in ("high", "liquid", "ample")):
        liquidity_score = 0
    elif any(token in liquidity for token in ("low", "thin", "illiquid")):
        liquidity_score = 2
    elif any(token in liquidity for token in ("medium", "normal", "moderate")):
        liquidity_score = 1
    else:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["liquidity state is not classified"]
        return result

    if any(token in volatility for token in ("high", "elevated")):
        volatility_score = 2
    elif any(token in volatility for token in ("medium", "normal", "moderate")):
        volatility_score = 1
    elif any(token in volatility for token in ("low", "quiet")):
        volatility_score = 0
    else:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["volatility state is not classified"]
        return result

    if any(token in urgency for token in ("high", "urgent")):
        urgency_score = 2
    elif any(token in urgency for token in ("medium", "normal", "moderate")):
        urgency_score = 1
    elif any(token in urgency for token in ("low", "patient")):
        urgency_score = 0
    else:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["urgency is not classified"]
        return result

    if any(token in momentum for token in ("neutral", "flat", "none")):
        momentum_score = 1
        momentum_alignment = "NEUTRAL"
    elif (candidate_side == "BUY" and any(token in momentum for token in ("up", "bull", "positive", "rising"))) or (candidate_side == "SELL" and any(token in momentum for token in ("down", "bear", "negative", "falling"))):
        momentum_score = 0
        momentum_alignment = "FAVORABLE"
    elif (candidate_side == "BUY" and any(token in momentum for token in ("down", "bear", "negative", "falling"))) or (candidate_side == "SELL" and any(token in momentum for token in ("up", "bull", "positive", "rising"))):
        momentum_score = 2
        momentum_alignment = "ADVERSE"
    else:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["price momentum direction is not classifiable against the candidate side"]
        return result

    size_score = 0 if size_to_adv < 0.01 else 2 if size_to_adv > 0.25 else 1
    difficulty_score = size_score + liquidity_score + volatility_score + momentum_score + urgency_score
    difficulty = "HIGH" if difficulty_score >= 6 else "MODERATE" if difficulty_score >= 3 else "LOW"
    result["johnson_order_size_to_adv"] = size_to_adv
    result["johnson_momentum_alignment"] = momentum_alignment
    result["johnson_order_difficulty_score"] = difficulty_score
    result["johnson_order_difficulty"] = difficulty
    result["view"] = "WAIT"
    result["reasons"] = ["order difficulty combines observed size, liquidity, volatility, momentum, urgency, and horizon context"]
    return result
