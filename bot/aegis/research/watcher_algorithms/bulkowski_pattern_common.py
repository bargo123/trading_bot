"""Shared validation for individually authored Bulkowski Watcher rules."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ._common import absent, base, first, normalized_status, number, values, with_direction

SOURCE = "Thomas N. Bulkowski — Encyclopedia of Chart Patterns"


def start(algorithm_id: str, state: Mapping[str, Any], keys: Sequence[str]):
    """Require complete observed pattern inputs before applying a rule."""
    missing = [key for key in keys if first(state, key) is None]
    provenance = normalized_status(first(state, "bulkowski_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("bulkowski_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(algorithm_id, state, (SOURCE,), keys, missing)
    return base(algorithm_id, state, (SOURCE,), [key for key, _ in values(state, *keys)])


def direction(state: Mapping[str, Any], key: str) -> str | None:
    value = normalized_status(first(state, key))
    if value in {"up", "upward", "bullish", "buy", "long", "breakout up"}:
        return "UP"
    if value in {"down", "downward", "bearish", "sell", "short", "breakout down"}:
        return "DOWN"
    return None


def observed_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "valid"}


def finite(values_to_check: Sequence[Any]) -> bool:
    return all(number(value) is not None for value in values_to_check)


def finish(result: dict[str, Any], state: Mapping[str, Any], signal: str, reason: str) -> dict[str, Any]:
    return with_direction(result, state, signal, reason)
