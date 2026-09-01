"""Timestamped cross-asset confirmation perspective for the read-only Watcher.

Intermarket analysis is contextual evidence: the copied state must identify
the observed markets and their as-of time. This evaluator does not infer a
currency or product relationship from a symbol name and never authorizes an
order.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
import re

from ._common import absent, base, direction, explicitly_confirmed, explicitly_observed, first, normalized_status, text, values, with_direction

ALGORITHM_ID = "intermarket_analysis"
SOURCES = (
    "John J. Murphy — Trading with Intermarket Analysis",
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Kathy Lien — Day Trading and Swing Trading the Currency Market",
)
KEYS = (
    "intermarket_signal",
    "intermarket_confirmation",
    "intermarket_provenance",
    "intermarket_as_of",
    "intermarket_observations",
    "dollar_index_direction",
    "bond_direction",
    "yield_direction",
    "commodity_direction",
    "stock_index_direction",
    "risk_on_off",
    "intermarket_state",
    "intermarket_conflict",
)
_OBSERVATION_KEYS = (
    "dollar_index_direction",
    "bond_direction",
    "yield_direction",
    "commodity_direction",
    "stock_index_direction",
    "risk_on_off",
)


def _valid_as_of(value) -> bool:
    stamp = text(value)
    if not stamp:
        return False
    try:
        datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    return True


def _has_phrase(value: str, phrase: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?![a-z])", value))


def _usable_observation(value) -> bool:
    if value is None or value in ("", {}, []):
        return False
    if isinstance(value, str):
        label = normalized_status(value)
        if not label or any(
            _has_phrase(label, marker)
            for marker in ("unknown", "unavailable", "missing", "synthetic", "proxy", "invalid")
        ):
            return False
    return True


def _observation_count(state) -> int:
    explicit = first(state, "intermarket_observations")
    if isinstance(explicit, Mapping):
        count = sum(_usable_observation(value) for value in explicit.values())
        if count >= 2:
            return count
    elif isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes, bytearray)):
        count = sum(_usable_observation(value) for value in explicit)
        if count >= 2:
            return count
    return sum(_usable_observation(first(state, key)) for key in _OBSERVATION_KEYS)


def _conflicted(state) -> bool:
    labels = [normalized_status(first(state, key)) for key in ("intermarket_state", "intermarket_conflict")]
    if any(
        _has_phrase(label, marker)
        for label in labels
        for marker in ("not conflict", "not conflicting", "no conflict", "no contradiction", "stable")
    ):
        return False
    return any(
        _has_phrase(label, marker)
        for label in labels
        for marker in ("conflict", "conflicted", "contradict", "divergent", "mixed", "unstable")
    )


def _signal(value) -> str | None:
    label = normalized_status(value)
    if any(_has_phrase(label, marker) for marker in ("not buy", "not sell", "unresolved", "unknown", "missing", "invalid")):
        return None
    return direction(value)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("timestamped_intermarket_evidence",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = _signal(first(state, "intermarket_signal"))
    confirmation = first(state, "intermarket_confirmation")
    provenance = first(state, "intermarket_provenance")
    as_of = first(state, "intermarket_as_of")
    if signal is None or not explicitly_confirmed(confirmation):
        result["intermarket_assessment"] = "UNKNOWN"
        result["view"] = "WAIT"
        result["reasons"] = ["intermarket direction lacks an explicit confirmed signal"]
        return result
    if not _valid_as_of(as_of):
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["timestamped_intermarket_as_of"]
        result["reasons"] = ["intermarket evidence must have a valid point-in-time timestamp"]
        return result
    if _observation_count(state) < 2:
        result["applicability"] = "MISSING_DATA"
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["independent_cross_asset_observations"]
        result["reasons"] = ["intermarket confirmation requires at least two observed cross-asset inputs"]
        return result
    if not explicitly_observed(
        provenance,
        accepted=("point in time cross asset", "timestamped intermarket", "verified cross asset"),
    ):
        result["intermarket_assessment"] = "UNKNOWN"
        result["view"] = "WAIT"
        result["warnings"] = ["intermarket provenance is synthetic, proxy, or unverified"]
        result["reasons"] = ["cross-asset evidence is not sufficiently observed to support a directional view"]
        return result
    if _conflicted(state):
        result["intermarket_assessment"] = "CONFLICTED"
        result["view"] = "WAIT"
        result["reasons"] = ["cross-asset inputs explicitly conflict or are unstable"]
        return result
    result["intermarket_assessment"] = "CONFIRMED"
    result["observation_count"] = _observation_count(state)
    return with_direction(result, state, signal, "timestamped cross-asset evidence confirms the recorded intermarket signal")
