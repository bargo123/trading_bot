"""Pole's catastrophe-move completion and exit-readiness perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "pole_catastrophe_exit"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "evaluation_phase",
    "pole_catastrophe_build_direction",
    "pole_catastrophe_reversal_spike_direction",
    "pole_catastrophe_reversal_spike_confirmed",
    "pole_catastrophe_elapsed_periods",
    "pole_catastrophe_exit_duration_periods",
    "pole_catastrophe_move_magnitude",
    "pole_catastrophe_min_exit_magnitude",
    "pole_catastrophe_exit_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        first(state, "pole_catastrophe_exit_data_provenance"),
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("pole_catastrophe_exit_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    phase = normalized_status(first(state, "evaluation_phase"))
    if phase not in {"open trade", "post entry", "trade management"}:
        result["applicability"] = "NOT_APPLICABLE"
        result["view"] = "NOT_APPLICABLE"
        result["reasons"] = ["catastrophe completion is an open-trade management study, not a pre-entry signal"]
        return result

    build_direction = normalized_status(first(state, "pole_catastrophe_build_direction"))
    spike_direction = normalized_status(first(state, "pole_catastrophe_reversal_spike_direction"))
    elapsed = number(first(state, "pole_catastrophe_elapsed_periods"))
    exit_duration = number(first(state, "pole_catastrophe_exit_duration_periods"))
    magnitude = number(first(state, "pole_catastrophe_move_magnitude"))
    min_magnitude = number(first(state, "pole_catastrophe_min_exit_magnitude"))
    if build_direction not in {"up", "down"} or spike_direction not in {"up", "down"}:
        result["pole_catastrophe_exit_action"] = "INVALID_DIRECTION"
        result["reasons"] = ["catastrophe completion needs observed up/down buildup and reversal directions"]
        return result
    if (
        elapsed is None
        or exit_duration is None
        or magnitude is None
        or min_magnitude is None
        or elapsed < 0
        or exit_duration <= 0
        or magnitude < 0
        or min_magnitude <= 0
    ):
        result["pole_catastrophe_exit_action"] = "INVALID_EXIT_INPUT"
        result["reasons"] = ["catastrophe completion needs finite non-negative observations and positive thresholds"]
        return result

    opposite_spike = spike_direction != build_direction
    duration_reached = elapsed >= exit_duration
    magnitude_reached = magnitude >= min_magnitude
    result.update(
        {
            "pole_catastrophe_build_direction": build_direction.upper(),
            "pole_catastrophe_reversal_spike_direction": spike_direction.upper(),
            "pole_catastrophe_opposite_spike": opposite_spike,
            "pole_catastrophe_duration_reached": duration_reached,
            "pole_catastrophe_magnitude_reached": magnitude_reached,
            "pole_catastrophe_duration_ratio": elapsed / exit_duration,
            "pole_catastrophe_magnitude_ratio": magnitude / min_magnitude,
        }
    )
    if not opposite_spike or not explicitly_confirmed(first(state, "pole_catastrophe_reversal_spike_confirmed")):
        result["pole_catastrophe_exit_action"] = "WAIT_FOR_OPPOSITE_SPIKE"
        result["reasons"] = ["a confirmed spike opposite the catastrophe buildup is required before completion"]
        return result
    if duration_reached and magnitude_reached:
        result["pole_catastrophe_exit_action"] = "EXIT_READY"
        result["reasons"] = [
            "confirmed opposite spike and both observed duration and magnitude conditions support catastrophe completion"
        ]
    else:
        result["pole_catastrophe_exit_action"] = "CONTINUE_MONITORING_DURATION_AND_MAGNITUDE"
        result["reasons"] = [
            "catastrophe reversal is confirmed but its duration-and-magnitude completion conditions are incomplete"
        ]
    result["warnings"] = [
        "exit readiness is a research observation; the Watcher cannot close broker positions"
    ]
    return result
