"""Nison two-black-gapping-candles continuation perspective."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_two_black_gapping"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_gapping_window_direction",
    "nison_gapping_window_confirmed",
    "nison_gapping_window_filled",
    "nison_gapping_first_body_color",
    "nison_gapping_second_body_color",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "nison_gapping_window_direction")) != "falling":
        result["view"] = "WAIT"
        result["reasons"] = ["two-black-gapping pattern requires a falling window"]
        return result
    if not volman_truth(first(state, "nison_gapping_window_confirmed")) or volman_truth(first(state, "nison_gapping_window_filled")):
        result["view"] = "WAIT"
        result["reasons"] = ["falling window must be confirmed and remain unfilled for the gapping sequence"]
        return result
    colors = {
        normalized_status(first(state, "nison_gapping_first_body_color")),
        normalized_status(first(state, "nison_gapping_second_body_color")),
    }
    if colors != {"black"}:
        result["view"] = "WAIT"
        result["reasons"] = ["both candles immediately after the falling window must have black real bodies"]
        return result
    result["nison_two_black_gapping_assessment"] = "CONFIRMED_BEARISH_GAP_SEQUENCE"
    return with_direction(result, state, "SELL", "a confirmed falling window was followed by two black real bodies")
