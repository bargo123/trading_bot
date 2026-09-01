"""Al Brooks' always-in trend-mode context."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, values, volman_truth, with_direction

ALGORITHM_ID = "brooks_always_in_mode"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "side",
    "brooks_always_in_mode",
    "brooks_always_in_direction",
    "brooks_always_in_spike_confirmed",
    "brooks_always_in_data_provenance",
)


def _brooks_provenance_ok(value) -> bool:
    # The feature adapter's completed quote bars are an observed, explicitly
    # labelled proxy for chart bars.  Accept that one exact provenance label;
    # synthetic, fixture, and unverified labels remain fail-closed.
    return normalized_status(value) == "completed quote bar proxy" or explicitly_observed(
        value,
        accepted=("observed", "measured", "historical", "timestamped"),
    )


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _brooks_provenance_ok(first(state, "brooks_always_in_data_provenance")):
        missing.append("brooks_always_in_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["view"] = "WAIT"
    side = normalized_status(first(state, "side")).upper()
    direction = normalized_status(first(state, "brooks_always_in_direction"))
    if side not in {"BUY", "SELL"} or direction not in {"up", "down"}:
        result["reasons"] = ["always-in mode needs a directional candidate and directional market mode"]
        return result
    if not volman_truth(first(state, "brooks_always_in_mode")):
        result["reasons"] = ["the market is not observed in always-in mode"]
        return result
    if not volman_truth(first(state, "brooks_always_in_spike_confirmed")):
        result["reasons"] = ["the source requires a directional spike before treating always-in mode as actionable context"]
        return result
    signal = "BUY" if direction == "up" else "SELL"
    result["brooks_always_in_assessment"] = "ALWAYS_IN_DIRECTION_CONFIRMED"
    return with_direction(result, state, signal, "directional always-in mode and its spike confirmation agree")
