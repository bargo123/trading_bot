"""Real-volume market-profile auction perspective."""
from __future__ import annotations

from collections.abc import Mapping

from ._common import base, direction, explicitly_observed, first, normalized_status, text, values, with_direction

ALGORITHM_ID = "market_profile"
SOURCES = (
    "James Dalton — Markets in Profile",
    "James Dalton — Mind Over Markets",
    "Frank de Jong — The Microstructure of Financial Markets",
)
KEYS = (
    "market_profile",
    "profile_data_provenance",
    "profile_signal",
    "auction_state",
    "value_area",
    "poc",
)


def _negative_label(value) -> bool:
    normalized = normalized_status(value)
    return any(
        marker in normalized
        for marker in (
            "proxy", "synthetic", "unverified", "unknown", "missing", "unavailable",
            "not ", "no ", "without ", "unconfirmed", "failed", "invalid",
            "neutral", "ambiguous",
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
            missing_inputs=("real_volume_profile",),
        )
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    profile = first(state, "market_profile")
    provenance = text(first(state, "profile_data_provenance"))
    provenance_labels = [provenance]
    if isinstance(profile, Mapping):
        provenance_labels.extend([text(profile.get("source")), text(profile.get("provenance"))])
    if not isinstance(profile, Mapping) or any(_negative_label(label) for label in provenance_labels if label) or not any(
        explicitly_observed(
            label,
            accepted=("real volume profile", "exchange volume profile", "actual volume profile", "traded volume profile"),
        )
        for label in provenance_labels
    ):
        result["view"] = "WAIT"
        result["warnings"] = ["price/tick proxy is not an observed volume profile"]
        result["reasons"] = ["directional auction evidence requires real volume-profile provenance"]
        return result
    signal_value = first(state, "profile_signal") or first(state, "auction_state")
    if signal_value is not None and _negative_label(signal_value):
        result["view"] = "WAIT"
        result["reasons"] = ["auction direction is negated or unresolved"]
        return result
    signal = direction(signal_value)
    if signal:
        return with_direction(result, state, signal, "real-volume profile records a directional auction signal")
    result["view"] = "WAIT"
    result["reasons"] = ["real-volume profile is present but auction direction is unresolved"]
    return result
