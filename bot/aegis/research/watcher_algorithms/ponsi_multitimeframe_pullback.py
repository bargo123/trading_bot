"""Ponsi's long-trend, lower-timeframe pullback perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_multitimeframe_pullback"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "side",
    "ponsi_long_term_trend",
    "ponsi_short_term_location",
    "ponsi_short_term_oscillator",
    "ponsi_oscillator_transition",
    "ponsi_mtf_data_provenance",
)


def _direction(value: object) -> str | None:
    normalized = normalized_status(value)
    if normalized in {"up", "uptrend", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downtrend", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def _turns(value: object, expected: str) -> bool:
    normalized = normalized_status(value)
    if expected == "BUY":
        return normalized in {"rising", "rising to neutral", "oversold to neutral", "bullish turn", "up"}
    return normalized in {"falling", "falling to neutral", "overbought to neutral", "bearish turn", "down"}


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in ("side", "ponsi_long_term_trend", "ponsi_mtf_data_provenance") if first(state, key) is None]
    location = normalized_status(first(state, "ponsi_short_term_location"))
    oscillator = normalized_status(first(state, "ponsi_short_term_oscillator"))
    transition = first(state, "ponsi_oscillator_transition")
    if not location and not (oscillator and transition is not None):
        missing.append("ponsi_short_term_trigger")
    if not explicitly_observed(first(state, "ponsi_mtf_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("ponsi_mtf_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    trend = _direction(first(state, "ponsi_long_term_trend"))
    candidate_side = str(first(state, "side") or "").upper()
    if trend is None:
        result["ponsi_mtf_assessment"] = "LONG_TERM_TREND_UNRESOLVED"
        result["reasons"] = ["the long-term chart does not establish a directional trend"]
        return result
    if candidate_side != trend:
        result["ponsi_mtf_assessment"] = "LONG_TERM_DIRECTION_CONFLICT"
        result["reasons"] = ["Ponsi permits entries only in the direction of the longer-timeframe trend"]
        return result

    aligned_location = (trend == "BUY" and location in {"support", "at support", "support area"}) or (
        trend == "SELL" and location in {"resistance", "at resistance", "resistance area"}
    )
    oscillator_trigger = False
    if oscillator in {"oversold", "overbought"}:
        oscillator_trigger = (trend == "BUY" and oscillator == "oversold" and _turns(transition, "BUY")) or (
            trend == "SELL" and oscillator == "overbought" and _turns(transition, "SELL")
        )
    if not aligned_location and not oscillator_trigger:
        result["ponsi_mtf_assessment"] = "LOWER_TIMEFRAME_TRIGGER_MISSING"
        result["reasons"] = ["the lower timeframe has neither an aligned support/resistance location nor an oscillator turn"]
        return result
    result["ponsi_mtf_assessment"] = "TREND_ALIGNED_PULLBACK"
    return with_direction(result, state, trend, "long-term trend agrees with a lower-timeframe support/resistance or oscillator pullback trigger")
