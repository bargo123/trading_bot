"""Ponsi squeeze play: contracting volatility followed by a confirmed break."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ponsi_squeeze_play"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "ponsi_ema20_slope",
    "ponsi_atr_trend",
    "ponsi_bollinger_width_trend",
    "ponsi_consolidation_bars",
    "ponsi_breakout_direction",
    "ponsi_breakout_confirmation",
    "ponsi_data_provenance",
)


def _direction(value) -> str | None:
    value = normalized_status(value)
    if value in {"up", "upside", "buy", "long", "bull", "bullish"}:
        return "BUY"
    if value in {"down", "downside", "sell", "short", "bear", "bearish"}:
        return "SELL"
    return None


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("contracting_volatility_breakout",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if not explicitly_observed(first(state, "ponsi_data_provenance"), accepted=("observed", "measured", "timestamped", "journal")):
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["ponsi_data_provenance"]
        result["reasons"] = ["the squeeze requires observed timestamped volatility evidence"]
        return result
    bars = number(first(state, "ponsi_consolidation_bars"))
    if bars is None or bars <= 0:
        result["view"] = "WAIT"
        result["ponsi_squeeze_assessment"] = "CONSOLIDATION_NOT_CONFIRMED"
        result["reasons"] = ["the squeeze needs a measured consolidation interval"]
        return result
    slope = normalized_status(first(state, "ponsi_ema20_slope"))
    atr = normalized_status(first(state, "ponsi_atr_trend"))
    width = normalized_status(first(state, "ponsi_bollinger_width_trend"))
    if slope not in {"flat", "sideways", "flattening"} or atr != "falling" or width != "falling":
        result["view"] = "WAIT"
        result["ponsi_squeeze_assessment"] = "VOLATILITY_NOT_CONTRACTING"
        result["reasons"] = ["the source confirms the squeeze with a flat EMA and falling ATR and Bollinger width"]
        return result
    if not (explicitly_confirmed(first(state, "ponsi_breakout_confirmation")) or normalized_status(first(state, "ponsi_breakout_confirmation")) in {"true", "yes"}):
        result["view"] = "WAIT"
        result["ponsi_squeeze_assessment"] = "BREAKOUT_NOT_CONFIRMED"
        result["reasons"] = ["contracting volatility has no confirmed trend-line breakout yet"]
        return result
    breakout = _direction(first(state, "ponsi_breakout_direction"))
    if breakout is None:
        result["view"] = "WAIT"
        result["ponsi_squeeze_assessment"] = "BREAKOUT_DIRECTION_MISSING"
        result["reasons"] = ["the squeeze is direction-neutral until a break direction is observed"]
        return result
    result["ponsi_squeeze_assessment"] = "CONFIRMED_BREAKOUT"
    return with_direction(result, state, breakout, "flat EMA, falling ATR, falling Bollinger width, and a confirmed directional breakout are observed")
