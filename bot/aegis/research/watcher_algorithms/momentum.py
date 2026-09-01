"""Directional momentum perspective using point-in-time follow-through."""
from __future__ import annotations

from ._common import base, direction, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "momentum"
SOURCES = (
    "Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",
    "Ernest Chan — Machine Trading",
    "Robert Carver — Systematic Trading",
)
KEYS = (
    "momentum",
    "momentum_direction",
    "momentum_context",
    "roc_direction",
    "follow_through",
    "momentum_decay",
    "exhaustion",
)


def _negative_label(value) -> bool:
    normalized = normalized_status(value)
    return any(
        marker in normalized
        for marker in (
            "not ", "no ", "without ", "unconfirmed", "failed", "invalid",
            "unknown", "flat", "neutral", "ambiguous",
        )
    )


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(
            ALGORITHM_ID,
            state,
            SOURCES,
            KEYS,
            applicability="MISSING_DATA",
            view="MISSING_DATA",
            missing_inputs=("momentum_and_follow_through",),
        )
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    decay = normalized_status(first(state, "momentum_decay", "exhaustion"))
    if decay and decay not in {"none", "false", "no", "absent", "not observed"}:
        result["view"] = "WAIT"
        result["reasons"] = ["momentum decay or exhaustion is present"]
        return result

    follow_through = normalized_status(first(state, "follow_through"))
    if not follow_through or _negative_label(follow_through) or follow_through in {"absent", "false", "none"}:
        result["view"] = "WAIT"
        result["reasons"] = ["directional momentum lacks explicit follow-through"]
        return result

    direction_value = first(state, "momentum_direction", "roc_direction", "momentum_context")
    if direction_value is not None and _negative_label(direction_value):
        result["view"] = "WAIT"
        result["reasons"] = ["directional momentum label is negated or unresolved"]
        return result
    signal = direction(direction_value)
    momentum_value = number(first(state, "momentum"))
    numeric_signal = "BUY" if momentum_value is not None and momentum_value > 0 else "SELL" if momentum_value is not None and momentum_value < 0 else None
    if signal and numeric_signal and signal != numeric_signal:
        result["view"] = "WAIT"
        result["reasons"] = ["directional momentum labels conflict with the measured value"]
        return result
    signal = signal or numeric_signal
    if signal is None:
        result["view"] = "WAIT"
        result["reasons"] = ["momentum direction is unavailable or flat"]
        return result
    result = with_direction(result, state, signal, "directional momentum and follow-through are observed")
    if momentum_value is not None:
        result["momentum_value"] = momentum_value
    return result
