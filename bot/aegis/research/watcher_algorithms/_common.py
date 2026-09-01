"""Small read-only helpers shared by individually authored Watcher rules."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

BUY_WORDS = ("buy", "bull", "bullish", "up", "uptrend", "higher high", "higher low", "long", "positive", "rising", "breakout up")
SELL_WORDS = ("sell", "bear", "bearish", "down", "downtrend", "lower high", "lower low", "short", "negative", "falling", "breakout down")


class CachedState(Mapping[str, Any]):
    """Read-only state view that reuses nested context lookups per scan row."""

    __slots__ = ("_state", "_contexts", "_values")

    def __init__(self, state: Mapping[str, Any]) -> None:
        self._state = state
        self._contexts: tuple[Mapping[str, Any], ...] | None = None
        self._values: dict[tuple[str, ...], list[tuple[str, Any]]] = {}

    def __getitem__(self, key: str) -> Any:
        return self._state[key]

    def __iter__(self):
        return iter(self._state)

    def __len__(self) -> int:
        return len(self._state)

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def contexts(self) -> tuple[Mapping[str, Any], ...]:
        if self._contexts is None:
            self._contexts = tuple(_contexts_uncached(self._state))
        return self._contexts

    def values_for(self, keys: tuple[str, ...]) -> list[tuple[str, Any]]:
        found = self._values.get(keys)
        if found is None:
            found = _values_uncached(self.contexts(), keys)
            self._values[keys] = found
        return found


def text(value: Any) -> str:
    return str(value or "").strip()


def normalized_status(value: Any) -> str:
    """Normalize status/provenance labels without turning negations positive."""
    return re.sub(r"[_-]+", " ", text(value).lower()).strip()


def _has_phrase(value: str, phrase: str) -> bool:
    normalized_phrase = normalized_status(phrase)
    if not normalized_phrase:
        return False
    return bool(re.search(r"(?<![a-z])" + re.escape(normalized_phrase) + r"(?![a-z])", value))


def explicitly_validated(value: Any, *, accepted: Sequence[str] = ("validated", "valid")) -> bool:
    """Return true only for an explicit positive validation label.

    Substring checks are unsafe here: ``not_validated`` contains ``validated``
    and ``unverified`` contains ``verified``.  Watcher perspectives must stay
    conservative when upstream evidence is negated or failed.
    """
    normalized = normalized_status(value)
    if not normalized:
        return False
    rejected = (
        "invalid",
        "unvalidated",
        "unverified",
        "not valid",
        "not validated",
        "not verified",
        "not stationary",
        "not observed",
        "failed",
        "missing",
        "unavailable",
    )
    if any(_has_phrase(normalized, phrase) for phrase in rejected):
        return False
    return any(_has_phrase(normalized, phrase) for phrase in accepted)


def explicitly_confirmed(value: Any) -> bool:
    """Return true only for an explicit, non-negated confirmation label."""
    normalized = normalized_status(value)
    if not normalized:
        return False
    rejected = (
        "unconfirmed",
        "not confirmed",
        "no confirmation",
        "missing confirmation",
        "without confirmation",
        "confirmation unavailable",
        "failed",
        "rejected",
        "invalid",
    )
    if any(_has_phrase(normalized, phrase) for phrase in rejected):
        return False
    return any(_has_phrase(normalized, phrase) for phrase in ("confirmed", "confirmation", "confirm"))


def explicitly_calibrated(value: Any) -> bool:
    """Return true only for a positive calibrated label, never ``uncalibrated``."""
    normalized = normalized_status(value)
    if not normalized or any(
        _has_phrase(normalized, phrase)
        for phrase in ("uncalibrated", "not calibrated", "calibration failed", "failed", "missing", "unavailable")
    ):
        return False
    return _has_phrase(normalized, "calibrated")


def explicitly_observed(value: Any, *, accepted: Sequence[str]) -> bool:
    """Require a positive observation/provenance label without proxy aliases."""
    normalized = normalized_status(value)
    if not normalized or any(
        _has_phrase(normalized, phrase)
        for phrase in (
            "proxy", "synthetic", "unverified", "unreal", "unknown",
            "missing", "unavailable", "not real", "not observed",
        )
    ):
        return False
    return any(_has_phrase(normalized, phrase) for phrase in accepted)


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _contexts_uncached(state: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = [state]
    for key in ("context", "entry_state", "decision_snapshot", "m1_context", "m5_context", "m15_context", "h1_context", "structure_context", "volatility_context", "microstructure", "quote_tick_dynamics", "volume_context", "short_returns"):
        value = state.get(key)
        if isinstance(value, Mapping):
            result.append(value)
    return result


def contexts(state: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    if isinstance(state, CachedState):
        return state.contexts()
    return _contexts_uncached(state)


def _present(value: Any) -> bool:
    """Treat empty containers/whitespace as unavailable, while preserving 0/False."""
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        return bool(normalized) and normalized not in {
            "unknown", "unavailable", "not_available", "not_observed",
        } and not normalized.startswith(("unknown_", "unavailable_"))
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return bool(value)
    return True


def _values_uncached(context_list: Sequence[Mapping[str, Any]], keys: tuple[str, ...]) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for context in context_list:
        for key in keys:
            value = context.get(key)
            if key not in seen and _present(value):
                found.append((key, value))
                seen.add(key)
    return found


def values(state: Mapping[str, Any], *keys: str) -> list[tuple[str, Any]]:
    key_tuple = tuple(keys)
    if isinstance(state, CachedState):
        return state.values_for(key_tuple)
    return _values_uncached(contexts(state), key_tuple)


def first(state: Mapping[str, Any], *keys: str) -> Any:
    found = values(state, *keys)
    return found[0][1] if found else None


def strings(state: Mapping[str, Any], *keys: str) -> str:
    return " ".join(text(value).lower() for _, value in values(state, *keys))


def direction(value: Any) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", text(value).lower())
    if not normalized:
        return None
    has = lambda word: bool(re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", normalized))
    buy = any(has(word) for word in BUY_WORDS)
    sell = any(has(word) for word in SELL_WORDS)
    return "BUY" if buy and not sell else "SELL" if sell and not buy else None


def side(state: Mapping[str, Any]) -> str | None:
    value = text(first(state, "side", "position_side")).lower()
    return value.upper() if value in {"buy", "sell"} else None


def base(
    algorithm_id: str,
    state: Mapping[str, Any],
    sources: Sequence[str],
    inputs: Sequence[str],
    *,
    applicability: str = "APPLICABLE",
    view: str = "WAIT",
    reasons: Sequence[str] = (),
    warnings: Sequence[str] = (),
    missing_inputs: Sequence[str] = (),
) -> dict[str, Any]:
    result = {
        "algorithm_id": algorithm_id,
        "view": view,
        "candidate_side": side(state),
        "applicability": applicability,
        "reasons": list(reasons),
        "warnings": list(warnings),
        "missing_inputs": list(missing_inputs),
        "inputs_used": list(inputs),
        "source_books": list(sources),
        "execution_authority": False,
        "uses_future_data": False,
        "research_only": True,
        "no_lookahead": True,
    }
    provenance = state.get("feature_provenance")
    if isinstance(provenance, Mapping):
        result["feature_provenance"] = dict(provenance)
    return result


def with_direction(result: dict[str, Any], state: Mapping[str, Any], signal: str | None, reason: str) -> dict[str, Any]:
    candidate_side = side(state)
    if signal in {"BUY", "SELL"}:
        result["view"] = signal
        result["candidate_alignment"] = "SUPPORTS" if signal == candidate_side else "OPPOSES"
        result["reasons"] = [*result.get("reasons", []), reason]
    elif candidate_side:
        result["candidate_alignment"] = "UNRESOLVED"
    return result


def absent(algorithm_id: str, state: Mapping[str, Any], sources: Sequence[str], inputs: Sequence[str], missing: Sequence[str]) -> dict[str, Any]:
    return base(algorithm_id, state, sources, inputs, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=missing)


def volman_direction(state: Mapping[str, Any]) -> str | None:
    """Normalize the directional label used by the Volman quote-bar proxies."""
    value = normalized_status(first(state, "volman_signal_direction", "volman_break_direction", "volman_market_pressure", "volman_trend"))
    if any(_has_phrase(value, phrase) for phrase in ("up", "bull", "buy", "long")):
        return "up"
    if any(_has_phrase(value, phrase) for phrase in ("down", "bear", "sell", "short")):
        return "down"
    return None


def volman_truth(value: Any) -> bool:
    """Interpret an explicit boolean-like observation conservatively."""
    if isinstance(value, bool):
        return value
    normalized = normalized_status(value)
    return normalized in {"true", "yes", "confirmed", "observed", "held", "clear", "present", "valid"}


def volman_confirmed(state: Mapping[str, Any]) -> bool:
    return volman_truth(first(state, "volman_signal_break", "volman_signal_confirmation"))


def volman_has_setup(state: Mapping[str, Any], expected: str) -> bool:
    expected_normalized = normalized_status(expected)
    candidates: list[Any] = [first(state, "volman_setup")]
    raw_setups = first(state, "volman_setups")
    if isinstance(raw_setups, Sequence) and not isinstance(raw_setups, (str, bytes, bytearray)):
        candidates.extend(raw_setups)
    return any(normalized_status(value) == expected_normalized for value in candidates)


def volman_missing(state: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    """Return required Volman observations absent from a copied state."""
    missing = [key for key in keys if first(state, key) is None]
    provenance = normalized_status(first(state, "volman_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("volman_data_provenance")
    return list(dict.fromkeys(missing))


def vpa_missing(state: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    """Return required VPA observations absent from a copied state."""
    missing = [key for key in keys if first(state, key) is None]
    provenance = normalized_status(first(state, "vpa_volume_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("vpa_volume_provenance")
    return list(dict.fromkeys(missing))


def ponsi_missing(state: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    """Return missing inputs for causal Ponsi quote-bar proxies.

    A labelled quote-bar proxy is usable for Watcher research.  Synthetic or
    unavailable data is not promoted into a chart observation.
    """
    missing = [key for key in keys if first(state, key) is None]
    provenance = normalized_status(first(state, "ponsi_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("ponsi_data_provenance")
    return list(dict.fromkeys(missing))


def nison_missing(state: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    """Return missing inputs for causal Nison price-filtered chart proxies."""
    missing = [key for key in keys if first(state, key) is None]
    provenance = normalized_status(first(state, "nison_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("nison_data_provenance")
    return list(dict.fromkeys(missing))


def vpa_real_volume(state: Mapping[str, Any]) -> bool:
    provenance = normalized_status(first(state, "vpa_volume_provenance"))
    return any(_has_phrase(provenance, phrase) for phrase in ("real traded volume", "real volume", "exchange volume"))


def em_missing(state: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    """Return absent Edwards-Magee observations from a copied state."""
    missing = [key for key in keys if first(state, key) is None]
    provenance = normalized_status(first(state, "em_data_provenance"))
    if not provenance or any(token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")):
        missing.append("em_data_provenance")
    return list(dict.fromkeys(missing))


def em_real_volume(state: Mapping[str, Any]) -> bool:
    provenance = normalized_status(first(state, "em_volume_provenance"))
    return any(_has_phrase(provenance, phrase) for phrase in ("real traded volume", "real volume", "exchange volume"))
