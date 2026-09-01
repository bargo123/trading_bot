"""Chan's bid/ask-size imbalance momentum perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, values, with_direction

ALGORITHM_ID = "chan_bid_ask_imbalance"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_bid_size",
    "chan_ask_size",
    "chan_imbalance_min_ratio",
    "chan_imbalance_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "chan_imbalance_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("chan_imbalance_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    bid = number(first(state, "chan_bid_size"))
    ask = number(first(state, "chan_ask_size"))
    minimum = number(first(state, "chan_imbalance_min_ratio"))
    if bid is None or ask is None or minimum is None or bid <= 0 or ask <= 0 or minimum <= 1:
        result["chan_imbalance_assessment"] = "INVALID_BOOK_INPUT"
        result["view"] = "WAIT"
        result["reasons"] = ["bid and ask sizes must be positive and the imbalance ratio must exceed one"]
        return result
    ratio = bid / ask if bid >= ask else ask / bid
    result["chan_imbalance_ratio"] = ratio
    if ratio < minimum:
        result["chan_imbalance_assessment"] = "BALANCED_BOOK"
        result["view"] = "WAIT"
        result["reasons"] = ["observed bid/ask size imbalance is below the measured ratio threshold"]
        return result
    if bid > ask:
        result["chan_imbalance_assessment"] = "BID_PRESSURE"
        return with_direction(result, state, "BUY", "bid size materially exceeds ask size in the observed order book")
    result["chan_imbalance_assessment"] = "ASK_PRESSURE"
    return with_direction(result, state, "SELL", "ask size materially exceeds bid size in the observed order book")
