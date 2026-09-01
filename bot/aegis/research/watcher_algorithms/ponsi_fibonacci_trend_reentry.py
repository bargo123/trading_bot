"""Ponsi's Fibonacci retracement plus trend and oscillator re-entry study."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, volman_truth, with_direction

ALGORITHM_ID = "ponsi_fibonacci_trend_reentry"
SOURCES = ("Ed Ponsi — Forex Patterns & Probabilities",)
KEYS = (
    "side",
    "ponsi_primary_trend",
    "ponsi_fibonacci_ratio",
    "ponsi_fibonacci_level_role",
    "ponsi_fibonacci_at_level",
    "ponsi_short_oscillator_state",
    "ponsi_oscillator_transition",
    "ponsi_fibonacci_entry_confirmation",
    "ponsi_data_provenance",
)


def _direction(value: object) -> str | None:
    normalized = normalized_status(value)
    if normalized in {"up", "uptrend", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downtrend", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def _turn(value: object, signal: str) -> bool:
    normalized = normalized_status(value)
    accepted = {"rising to neutral", "oversold to neutral", "bullish turn", "rising", "up"} if signal == "BUY" else {
        "falling to neutral", "overbought to neutral", "bearish turn", "falling", "down"
    }
    return normalized in accepted


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(first(state, "ponsi_data_provenance"), accepted=("observed", "measured", "timestamped")):
        missing.append("ponsi_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    ratio = number(first(state, "ponsi_fibonacci_ratio"))
    if ratio is None or min(abs(ratio - level) for level in (0.382, 0.5, 0.618)) > 0.005:
        result["ponsi_fibonacci_assessment"] = "RETRACEMENT_RATIO_UNSUPPORTED"
        result["reasons"] = ["the retracement is not one of the source-defined 38.2%, 50%, or 61.8% areas"]
        return result
    signal = _direction(first(state, "ponsi_primary_trend"))
    if signal is None:
        result["ponsi_fibonacci_assessment"] = "PRIMARY_TREND_UNRESOLVED"
        result["reasons"] = ["the larger chart does not define the trend direction"]
        return result
    role = normalized_status(first(state, "ponsi_fibonacci_level_role"))
    aligned = (signal == "BUY" and role in {"support", "support area"}) or (
        signal == "SELL" and role in {"resistance", "resistance area"}
    )
    if not aligned or not volman_truth(first(state, "ponsi_fibonacci_at_level")):
        result["ponsi_fibonacci_assessment"] = "LEVEL_ALIGNMENT_MISSING"
        result["reasons"] = ["the retracement must be observed at a level that supports the trend-aligned entry"]
        return result
    oscillator = normalized_status(first(state, "ponsi_short_oscillator_state"))
    oscillator_matches = (signal == "BUY" and oscillator == "oversold") or (signal == "SELL" and oscillator == "overbought")
    if not oscillator_matches or not _turn(first(state, "ponsi_oscillator_transition"), signal):
        result["ponsi_fibonacci_assessment"] = "OSCILLATOR_TURN_MISSING"
        result["reasons"] = ["an extreme oscillator reading must turn toward neutral before the trend re-entry"]
        return result
    if not (volman_truth(first(state, "ponsi_fibonacci_entry_confirmation")) or normalized_status(first(state, "ponsi_fibonacci_entry_confirmation")) == "confirmed"):
        result["ponsi_fibonacci_assessment"] = "ENTRY_CONFIRMATION_MISSING"
        result["reasons"] = ["the retracement reaction has not been confirmed"]
        return result
    result["ponsi_fibonacci_assessment"] = "CONFIRMED_TREND_REENTRY"
    result["ponsi_fibonacci_ratio"] = ratio
    return with_direction(result, state, signal, "trend direction, Fibonacci support/resistance, and a confirmed oscillator turn agree")
