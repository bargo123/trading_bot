"""Velu, Hardy, and Nehren's RSI 70/30 reversal perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "velu_rsi_reversal"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_rsi_value",
    "velu_rsi_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_rsi_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("velu_rsi_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    rsi = number(first(state, "velu_rsi_value"))
    oversold = 30.0
    overbought = 70.0
    result.update(
        {
            "velu_rsi_value": rsi,
            "velu_rsi_oversold": oversold,
            "velu_rsi_overbought": overbought,
        }
    )
    if candidate_side is None or rsi is None or not 0.0 <= rsi <= 100.0:
        result["velu_rsi_action"] = "INVALID_RSI_INPUT"
        result["reasons"] = ["the RSI reversal perspective needs a finite observed RSI value between zero and 100"]
        return result
    if rsi < oversold:
        return with_direction(
            {**result, "velu_rsi_action": "OVERSOLD_BUY"},
            state,
            "BUY",
            "the observed RSI is below the source oversold level",
        )
    if rsi > overbought:
        return with_direction(
            {**result, "velu_rsi_action": "OVERBOUGHT_SELL"},
            state,
            "SELL",
            "the observed RSI is above the source overbought level",
        )
    result["velu_rsi_action"] = "INSIDE_NEUTRAL_ZONE"
    result["reasons"] = ["the observed RSI remains between the source 30/70 levels"]
    return result
