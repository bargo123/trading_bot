"""Chan's executable-quote data sufficiency check for high-frequency studies."""
from __future__ import annotations

import math
from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, normalized_status, values

ALGORITHM_ID = "chan_hft_quote_data_requirements"
SOURCES = ("Ernie Chan — Quantitative Trading",)
KEYS = (
    "chan_hft_bid_quotes",
    "chan_hft_ask_quotes",
    "chan_hft_last_quotes",
    "chan_hft_order_book_available",
    "chan_hft_quote_data_provenance",
)


def _series(value):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    if len(result) < 3 or any(item is None or not math.isfinite(item) for item in result):
        return None
    return result


def _boolean(value):
    if isinstance(value, bool):
        return value
    normalized = normalized_status(value)
    if normalized in {"true", "yes", "1", "available", "present"}:
        return True
    if normalized in {"false", "no", "0", "unavailable", "absent"}:
        return False
    return None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "chan_hft_quote_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        provenance,
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("chan_hft_quote_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    bids = _series(first(state, "chan_hft_bid_quotes"))
    asks = _series(first(state, "chan_hft_ask_quotes"))
    lasts = _series(first(state, "chan_hft_last_quotes"))
    book_available = _boolean(first(state, "chan_hft_order_book_available"))
    if bids is None or asks is None or lasts is None or book_available is None:
        result["chan_hft_data_action"] = "INVALID_QUOTE_DATA"
        result["reasons"] = [
            "bid, ask, and last must be finite sequences of at least three observations with an explicit book status"
        ]
        return result
    if not len(bids) == len(asks) == len(lasts):
        result["chan_hft_data_action"] = "INVALID_QUOTE_DATA"
        result["reasons"] = ["bid, ask, and last histories must have identical lengths"]
        return result
    if any(bid <= 0.0 or ask <= 0.0 or ask < bid for bid, ask in zip(bids, asks)):
        result["chan_hft_data_action"] = "INVALID_QUOTE_DATA"
        result["reasons"] = ["each observed quote must have positive prices and ask greater than or equal to bid"]
        return result

    spreads = [ask - bid for bid, ask in zip(bids, asks)]
    inside_fraction = sum(bid <= last <= ask for bid, ask, last in zip(bids, asks, lasts)) / len(lasts)
    result.update({
        "chan_hft_quote_observation_n": len(bids),
        "chan_hft_mean_spread": sum(spreads) / len(spreads),
        "chan_hft_last_inside_quote_fraction": inside_fraction,
        "chan_hft_order_book_available": book_available,
        "directional_claim": False,
    })
    if book_available:
        result["chan_hft_data_action"] = "QUOTE_DATA_READY"
        result["reasons"] = ["observed bid, ask, and last quotes are available for after-cost high-frequency study"]
    else:
        result["chan_hft_data_action"] = "QUOTE_DATA_READY_WITH_BOOK_LIMITATION"
        result["reasons"] = ["observed bid, ask, and last quotes are available but historical order-book depth is unavailable"]
        result["warnings"] = ["last-price quotes cannot reconstruct queue position or every depth-dependent execution outcome"]
    return result
