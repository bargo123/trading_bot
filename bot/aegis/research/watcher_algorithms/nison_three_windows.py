"""Nison three-window exhaustion with close-through confirmation."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "nison_three_windows"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_three_windows_direction",
    "nison_three_windows_count",
    "nison_three_windows_last_window_close",
    "nison_three_windows_confirmation",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "nison_three_windows_direction"))
    count = number(first(state, "nison_three_windows_count"))
    close = normalized_status(first(state, "nison_three_windows_last_window_close"))
    if count is None or count != int(count) or count < 3:
        result["view"] = "WAIT"
        result["reasons"] = ["three-window exhaustion requires at least three windows in one direction"]
        return result
    if not volman_truth(first(state, "nison_three_windows_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["three-window exhaustion requires a confirmed close through the last window"]
        return result
    if direction == "rising" and close == "below bottom":
        result["nison_three_windows_assessment"] = "RISING_THREE_WINDOWS_REVERSAL_CONFIRMED"
        return with_direction(result, state, "SELL", "three rising windows matured the advance and the last window broke on a close")
    if direction == "falling" and close == "above top":
        result["nison_three_windows_assessment"] = "FALLING_THREE_WINDOWS_REVERSAL_CONFIRMED"
        return with_direction(result, state, "BUY", "three falling windows matured the decline and the last window broke on a close")
    result["view"] = "WAIT"
    result["reasons"] = ["window direction and close-through direction do not confirm a reversal"]
    return result
