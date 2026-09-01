"""Aldridge quote-matching feasibility and after-cost perspective.

The source describes quote matching as dependent on identifying the order whose
placement moves the market.  Anonymous-market observations cannot establish
that premise, so this remains a conservative research diagnostic rather than
an executable signal.
"""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "aldridge_quote_matching"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_quote_match_identity_available",
    "aldridge_quote_match_direction",
    "aldridge_quote_match_persistence_confirmed",
    "aldridge_quote_match_probability",
    "aldridge_quote_match_expected_move",
    "aldridge_quote_match_total_cost",
    "aldridge_quote_match_data_provenance",
)


def _boolean(value):
    if isinstance(value, bool):
        return value
    label = normalized_status(value)
    if label in {"true", "yes", "available", "identified", "confirmed"}:
        return True
    if label in {"false", "no", "unavailable", "anonymous", "missing"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not side(state):
        missing.append("side")
    if not explicitly_observed(
        first(state, "aldridge_quote_match_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("aldridge_quote_match_data_provenance")
    identity = _boolean(first(state, "aldridge_quote_match_identity_available"))
    if identity is None:
        missing.append("aldridge_quote_match_identity_available")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    result["aldridge_quote_match_identity_available"] = identity

    direction = normalized_status(first(state, "aldridge_quote_match_direction"))
    probability = number(first(state, "aldridge_quote_match_probability"))
    expected_move = number(first(state, "aldridge_quote_match_expected_move"))
    total_cost = number(first(state, "aldridge_quote_match_total_cost"))
    if (
        direction not in {"up", "down"}
        or probability is None
        or not 0.0 <= probability <= 1.0
        or expected_move is None
        or expected_move <= 0.0
        or total_cost is None
        or total_cost < 0.0
    ):
        result["aldridge_quote_match_action"] = "INVALID_AFTER_COST_INPUTS"
        result["reasons"] = ["quote-matching direction, probability, move, and cost must be valid"]
        return result

    result["aldridge_quote_match_direction"] = direction
    result["aldridge_quote_match_probability"] = probability
    result["aldridge_quote_match_expected_move"] = expected_move
    result["aldridge_quote_match_total_cost"] = total_cost
    result["aldridge_quote_match_net_edge"] = (2.0 * probability - 1.0) * expected_move - total_cost

    if not identity:
        result["aldridge_quote_match_action"] = "ANONYMOUS_MARKET_INFEASIBLE"
        result["reasons"] = ["anonymous order flow cannot identify the market-moving quote"]
        return result
    if not explicitly_confirmed(first(state, "aldridge_quote_match_persistence_confirmed")):
        result["aldridge_quote_match_action"] = "PERSISTENCE_NOT_CONFIRMED"
        result["reasons"] = ["the identified quote impact is not persistent after the initial move"]
        return result
    if result["aldridge_quote_match_net_edge"] <= 0.0:
        result["aldridge_quote_match_action"] = "NO_POSITIVE_AFTER_COST_EDGE"
        result["reasons"] = ["directional forecast edge does not cover total executable cost"]
        return result

    result["aldridge_quote_match_action"] = "IDENTIFIED_PERSISTENT_IMPACT"
    result["directional_claim"] = True
    return with_direction(
        result,
        state,
        "BUY" if direction == "up" else "SELL",
        "identified quote impact persists and has positive forecast edge after cost",
    )
