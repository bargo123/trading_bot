"""Nison last-engulfing reversal with its required trend context."""
from __future__ import annotations

from ._common import absent, base, first, nison_missing, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "nison_last_engulfing"
SOURCES = ("Steve Nison — Beyond Candlesticks",)
KEYS = (
    "nison_last_engulfing_type",
    "nison_last_engulfing_trend",
    "nison_last_engulfing_body_color",
    "nison_last_engulfing_envelopes",
    "nison_last_engulfing_confirmation",
    "nison_last_engulfing_confirmation_direction",
    "nison_data_provenance",
)


def evaluate(state):
    missing = nison_missing(state, KEYS)
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not volman_truth(first(state, "nison_last_engulfing_envelopes")):
        result["view"] = "WAIT"
        result["reasons"] = ["last-engulfing candle must envelop the prior opposite body"]
        return result
    pattern = normalized_status(first(state, "nison_last_engulfing_type"))
    trend = normalized_status(first(state, "nison_last_engulfing_trend"))
    color = normalized_status(first(state, "nison_last_engulfing_body_color"))
    confirmation = normalized_status(first(state, "nison_last_engulfing_confirmation"))
    direction = normalized_status(first(state, "nison_last_engulfing_confirmation_direction"))
    if pattern == "bottom":
        if trend not in {"down", "downtrend", "decline", "falling"} or color != "black":
            result["view"] = "WAIT"
            result["reasons"] = ["last-engulfing bottom requires a black engulfing candle during a decline"]
            return result
        if confirmation != "close above black candle" or direction not in {"up", "bullish", "higher"}:
            result["view"] = "WAIT"
            result["reasons"] = ["last-engulfing bottom requires a close above the black candle"]
            return result
        result["nison_last_engulfing_assessment"] = "LAST_ENGULFING_BOTTOM_CONFIRMED"
        return with_direction(result, state, "BUY", "decline-context engulfing bottom reclaimed the black candle close")
    if pattern == "top":
        if trend not in {"up", "uptrend", "rally", "rising"} or color != "white":
            result["view"] = "WAIT"
            result["reasons"] = ["last-engulfing top requires a white engulfing candle during a rally"]
            return result
        if confirmation != "close below white candle" or direction not in {"down", "bearish", "lower"}:
            result["view"] = "WAIT"
            result["reasons"] = ["last-engulfing top requires a close below the white candle"]
            return result
        result["nison_last_engulfing_assessment"] = "LAST_ENGULFING_TOP_CONFIRMED"
        return with_direction(result, state, "SELL", "rally-context engulfing top broke below the white candle close")
    result["view"] = "WAIT"
    result["reasons"] = ["last-engulfing type is not bottom or top"]
    return result
