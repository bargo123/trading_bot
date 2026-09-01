"""Limit-order fill uncertainty and adverse-selection perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "harris_limit_order_regret"
SOURCES = ("Trading and Exchanges: Market Microstructure for Practitioners",)
KEYS = (
    "harris_limit_order_side",
    "harris_limit_price",
    "harris_best_bid",
    "harris_best_ask",
    "harris_limit_fill_probability",
    "harris_limit_adverse_move_probability",
    "harris_limit_expected_stand_s",
    "harris_limit_order_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("limit" in label or "order book" in label or "depth" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "harris_limit_order_provenance")):
        missing.append("harris_limit_order_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    side = normalized_status(first(state, "harris_limit_order_side")).upper()
    limit = number(first(state, "harris_limit_price"))
    bid = number(first(state, "harris_best_bid"))
    ask = number(first(state, "harris_best_ask"))
    fill = number(first(state, "harris_limit_fill_probability"))
    adverse = number(first(state, "harris_limit_adverse_move_probability"))
    stand = number(first(state, "harris_limit_expected_stand_s"))
    if (
        side not in {"BUY", "SELL"}
        or None in {limit, bid, ask, fill, adverse, stand}
        or bid >= ask
        or not 0 <= fill <= 1
        or not 0 <= adverse <= 1
        or stand < 0
    ):
        result["harris_limit_assessment"] = "UNKNOWN"
        result["reasons"] = ["limit-order regret requires valid executable prices and probability inputs"]
        return result
    if side == "BUY":
        placement = "AT_MARKET" if limit == bid else "BEHIND_MARKET" if limit < bid else "MARKETABLE"
    else:
        placement = "AT_MARKET" if limit == ask else "BEHIND_MARKET" if limit > ask else "MARKETABLE"
    result["harris_limit_placement"] = placement
    result["harris_execution_uncertainty"] = fill < adverse
    result["harris_limit_assessment"] = "HIGH_REGRET_RISK" if adverse > fill else "LOW_REGRET_RISK"
    result["reasons"] = [
        "standing limits trade execution certainty against adverse-selection regret"
    ]
    if result["harris_execution_uncertainty"]:
        result["warnings"] = ["observed adverse-move probability exceeds observed fill probability"]
    return result
