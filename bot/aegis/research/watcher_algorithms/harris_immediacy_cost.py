"""Immediacy-cost perspective from Harris's market microstructure text."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "harris_immediacy_cost"
SOURCES = ("Trading and Exchanges: Market Microstructure for Practitioners",)
KEYS = (
    "harris_best_bid",
    "harris_best_ask",
    "harris_order_side",
    "harris_execution_style",
    "harris_fee_per_unit",
    "harris_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("bbo" in label or "bid ask" in label or "executable" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "harris_data_provenance")):
        missing.append("harris_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    bid = number(first(state, "harris_best_bid"))
    ask = number(first(state, "harris_best_ask"))
    fee = number(first(state, "harris_fee_per_unit"))
    style = normalized_status(first(state, "harris_execution_style"))
    side = normalized_status(first(state, "harris_order_side")).upper()
    if None in {bid, ask, fee} or bid >= ask or fee < 0 or side not in {"BUY", "SELL"}:
        result["harris_immediacy_assessment"] = "UNKNOWN"
        result["reasons"] = ["immediacy requires a valid executable bid/ask and order side"]
        return result
    if style not in {"market", "marketable limit"}:
        result["harris_immediacy_assessment"] = "NOT_IMMEDIATE"
        result["reasons"] = ["the recorded order style does not demand immediate liquidity"]
        return result
    spread = ask - bid
    result["harris_half_spread"] = spread / 2.0
    result["harris_round_trip_spread_cost"] = spread
    result["harris_fee_per_unit"] = fee
    result["harris_immediacy_assessment"] = "MEASURED_COST"
    result["reasons"] = ["immediate market execution pays the observed spread, before any separate fee"]
    return result
