"""Dalton/Steidlmayer failed range-extension reversal perspective."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "dalton_failed_range_extension"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Peter Steidlmayer — Steidlmayer on Markets",
)
SOURCE_PAGES = "pp. 168-171"
KEYS = (
    "dalton_extension_direction",
    "dalton_initial_balance_high",
    "dalton_initial_balance_low",
    "dalton_auction_point_price",
    "dalton_close_price",
    "dalton_failed_extension_confirmed",
    "dalton_data_provenance",
)


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "dalton_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "proxy", "unknown", "unavailable")):
        missing.append("dalton_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "dalton_extension_direction"))
    high = number(first(state, "dalton_initial_balance_high"))
    low = number(first(state, "dalton_initial_balance_low"))
    auction = number(first(state, "dalton_auction_point_price"))
    close = number(first(state, "dalton_close_price"))
    if None in {high, low, auction, close} or low >= high:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["valid_initial_balance_extension_geometry"]
        return result
    if not volman_truth(first(state, "dalton_failed_extension_confirmed")):
        result["view"] = "WAIT"
        result["reasons"] = ["the failed extension requires a completed, confirmed close"]
        return result
    if direction == "up" and auction > high and close < auction:
        result["dalton_failed_extension_assessment"] = "FAILED_UP_EXTENSION"
        return with_direction(result, state, "SELL", "the upside auction point was breached but the close fell back below it")
    if direction == "down" and auction < low and close > auction:
        result["dalton_failed_extension_assessment"] = "FAILED_DOWN_EXTENSION"
        return with_direction(result, state, "BUY", "the downside auction point was breached but the close recovered above it")
    result["view"] = "WAIT"
    result["reasons"] = ["the auction point did not produce a confirmed failed range extension"]
    return result
