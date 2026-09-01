"""Velu, Hardy, and Nehren's moving-average oscillator cross rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, side, values, with_direction


ALGORITHM_ID = "velu_moving_average_oscillator"
SOURCES = ("Raja Velu, Maxence Hardy, Daniel Nehren — Algorithmic Trading and Quantitative Strategies",)
KEYS = (
    "side",
    "velu_oscillator_previous_short",
    "velu_oscillator_previous_long",
    "velu_oscillator_current_short",
    "velu_oscillator_current_long",
    "velu_oscillator_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "velu_oscillator_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("velu_oscillator_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    candidate_side = side(state)
    previous_short = number(first(state, "velu_oscillator_previous_short"))
    previous_long = number(first(state, "velu_oscillator_previous_long"))
    current_short = number(first(state, "velu_oscillator_current_short"))
    current_long = number(first(state, "velu_oscillator_current_long"))
    if any(value is None for value in (previous_short, previous_long, current_short, current_long)):
        result["velu_oscillator_action"] = "INVALID_OSCILLATOR_INPUT"
        result["reasons"] = ["the moving-average oscillator needs four finite observed averages"]
        return result

    previous_gap = previous_short - previous_long
    current_gap = current_short - current_long
    result.update(
        {
            "velu_oscillator_previous_gap": previous_gap,
            "velu_oscillator_current_gap": current_gap,
        }
    )
    if previous_gap <= 0.0 < current_gap:
        return with_direction(
            {**result, "velu_oscillator_action": "UPWARD_CROSS"},
            state,
            "BUY",
            "the observed short average crossed above the long average",
        )
    if previous_gap >= 0.0 > current_gap:
        return with_direction(
            {**result, "velu_oscillator_action": "DOWNWARD_CROSS"},
            state,
            "SELL",
            "the observed short average crossed below the long average",
        )
    result["velu_oscillator_action"] = "NO_CROSS"
    result["reasons"] = ["the observed short/long average relationship did not cross at this step"]
    return result
