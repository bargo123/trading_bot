"""Spike-and-channel trend/reversal perspective from Al Brooks."""
from __future__ import annotations

from ._common import absent, base, explicitly_confirmed, first, normalized_status, values, with_direction

ALGORITHM_ID = "al_brooks_spike_channel"
SOURCES = (
    "Al Brooks — Reading Price Charts Bar by Bar",
    "Al Brooks — Trading Price Action Trading Ranges",
)
KEYS = (
    "spike_channel_signal",
    "spike_channel_state",
    "spike_channel_test",
    "spike_channel_confirmation",
    "spike_channel_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("confirmed_spike_channel",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    signal = str(first(state, "spike_channel_signal") or "").strip().upper()
    state_label = normalized_status(first(state, "spike_channel_state"))
    test_label = normalized_status(first(state, "spike_channel_test"))
    provenance = normalized_status(first(state, "spike_channel_provenance"))
    if signal not in {"BUY", "SELL"} or "spike" not in state_label or "channel" not in state_label or not explicitly_confirmed(first(state, "spike_channel_confirmation")):
        result["view"] = "WAIT"
        result["reasons"] = ["spike-and-channel state and confirmation are incomplete"]
        return result
    if not any(token in test_label for token in ("held", "confirmed", "reclaimed", "resumed")):
        result["view"] = "WAIT"
        result["reasons"] = ["spike-and-channel test has not established a held or resumed state"]
        return result
    if any(token in provenance for token in ("synthetic", "proxy", "unverified", "unknown")):
        result["view"] = "WAIT"
        result["warnings"] = ["spike-and-channel provenance is synthetic, proxy, or unverified"]
        result["reasons"] = ["price-action continuation cannot be supported by proxy evidence"]
        return result
    return with_direction(result, state, signal, "confirmed spike-and-channel state has a held test")
