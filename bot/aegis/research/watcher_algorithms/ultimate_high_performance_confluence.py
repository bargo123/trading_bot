"""Anna Coulling's multi-signal high-performance confluence study."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ._common import absent, base, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "ultimate_high_performance_confluence"
SOURCES = ("Anna Coulling — The Ultimate Forex Trading System",)
KEYS = (
    "ultimate_confluence_signals",
    "ultimate_confluence_min_confirmations",
    "ultimate_data_provenance",
)


def _truthy(value):
    return value is True or normalized_status(value) in {
        "true", "yes", "confirmed", "observed", "valid",
    }


def _direction(value):
    normalized = normalized_status(value)
    if normalized in {"up", "upward", "bull", "bullish", "buy", "long"}:
        return "BUY"
    if normalized in {"down", "downward", "bear", "bearish", "sell", "short"}:
        return "SELL"
    return None


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = normalized_status(first(state, "ultimate_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ultimate_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    raw_signals = first(state, "ultimate_confluence_signals")
    minimum = number(first(state, "ultimate_confluence_min_confirmations"))
    if not isinstance(raw_signals, Sequence) or isinstance(raw_signals, (str, bytes, bytearray)) or minimum is None or minimum < 2:
        result["view"] = "WAIT"
        result["ultimate_confluence_assessment"] = "CONFLUENCE_INPUT_INVALID"
        result["reasons"] = ["at least two explicitly confirmed signal records are required"]
        return result
    confirmed = []
    for item in raw_signals:
        if not isinstance(item, Mapping):
            result["view"] = "WAIT"
            result["ultimate_confluence_assessment"] = "SIGNAL_RECORD_INVALID"
            result["reasons"] = ["each confluence signal must identify its direction and confirmation"]
            return result
        signal = _direction(item.get("direction"))
        if signal is None:
            result["view"] = "WAIT"
            result["ultimate_confluence_assessment"] = "SIGNAL_RECORD_INVALID"
            result["reasons"] = ["each confluence signal must have an explicit BUY or SELL direction"]
            return result
        if _truthy(item.get("confirmed")):
            confirmed.append((str(item.get("name") or "unnamed"), signal))
    result["ultimate_confluence_confirmed_count"] = len(confirmed)
    result["ultimate_confluence_confirmed_signals"] = [name for name, _ in confirmed]
    if len(confirmed) < int(minimum):
        result["view"] = "WAIT"
        result["ultimate_confluence_assessment"] = "INSUFFICIENT_CONFIRMED_SIGNALS"
        result["reasons"] = ["the observed number of agreeing confirmations is below the configured research requirement"]
        return result
    directions = {signal for _, signal in confirmed}
    if len(directions) != 1:
        result["view"] = "WAIT"
        result["ultimate_confluence_assessment"] = "SIGNAL_DISAGREEMENT"
        result["reasons"] = ["confirmed pattern, correlation, volume, or rejection signals disagree"]
        return result
    signal = next(iter(directions))
    result["ultimate_confluence_assessment"] = "CONFIRMED_CONFLUENCE"
    return with_direction(result, state, signal, "multiple independent observed signals agree on the same direction")
