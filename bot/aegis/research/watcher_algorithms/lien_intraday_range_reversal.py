"""Kathy Lien's multi-timeframe intraday range-reversal checklist."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "lien_intraday_range_reversal"
SOURCES = ("Kathy Lien — Day Trading and Swing Trading the Currency Market",)
KEYS = (
    "lien_environment",
    "lien_hourly_entry_context",
    "lien_daily_range_confirmed",
    "lien_oscillator",
    "lien_oscillator_state",
    "lien_key_level_behavior",
    "lien_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "lien_data_provenance")):
        missing.append("lien_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    if normalized_status(first(state, "lien_environment")) != "range":
        result["reasons"] = ["the intraday reversal checklist applies only when the higher-timeframe environment is a range"]
        return result
    if "range" not in normalized_status(first(state, "lien_hourly_entry_context")):
        result["reasons"] = ["the hourly entry context is not inside a confirmed range"]
        return result
    if first(state, "lien_daily_range_confirmed") is not True:
        result["reasons"] = ["the daily chart has not confirmed a range"]
        return result
    if normalized_status(first(state, "lien_oscillator")) not in {"rsi", "stochastics", "stochastic"}:
        result["reasons"] = ["the range entry needs an RSI or stochastic observation"]
        return result

    oscillator_state = normalized_status(first(state, "lien_oscillator_state"))
    level_behavior = normalized_status(first(state, "lien_key_level_behavior"))
    signal = None
    if oscillator_state in {"oversold reversal", "oversold confirmed", "oversold"} and level_behavior in {"support hold", "support held", "support bounce"}:
        signal = "BUY"
    elif oscillator_state in {"overbought reversal", "overbought confirmed", "overbought"} and level_behavior in {"resistance failure", "resistance failed", "resistance rejection"}:
        signal = "SELL"
    if signal is None:
        result["reasons"] = ["oscillator reversal and key support/resistance behavior do not agree on a range direction"]
        return result
    return with_direction(result, state, signal, "confirmed range, oscillator reversal, and key-level behavior agree")
