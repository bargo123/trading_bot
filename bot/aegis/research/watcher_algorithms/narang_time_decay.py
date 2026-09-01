"""Narang's delayed-entry/time-decay stress test (Inside the Black Box, ch. 9)."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "narang_time_decay"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "narang_delay_grid_s",
    "narang_delayed_entry_returns",
    "narang_time_decay_data_provenance",
)


def _series(value, *, minimum=2):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if len(result) >= minimum and all(item is not None for item in result) else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_time_decay_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("narang_time_decay_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    delays = _series(first(state, "narang_delay_grid_s"))
    returns = _series(first(state, "narang_delayed_entry_returns"))
    if delays is None or returns is None or len(delays) != len(returns):
        result["narang_time_decay_assessment"] = "INVALID_DELAY_REPLAY"
        result["reasons"] = ["delays and delayed-entry returns must be equally sized finite observations"]
        return result
    if any(later <= earlier for earlier, later in zip(delays, delays[1:])):
        result["narang_time_decay_assessment"] = "INVALID_DELAY_GRID"
        result["reasons"] = ["delay grid must be strictly increasing"]
        return result

    elapsed = delays[-1] - delays[0]
    slope = (returns[-1] - returns[0]) / elapsed
    result.update({
        "narang_time_decay_slope": slope,
        "narang_time_decay_first_return": returns[0],
        "narang_time_decay_last_return": returns[-1],
        "narang_time_decay_max_delay_s": delays[-1],
        "directional_claim": False,
    })
    if slope < 0.0 and returns[-1] < returns[0]:
        result["narang_time_decay_assessment"] = "DECAY_WITH_DELAY"
        result["reasons"] = ["measured implementation delay reduces the observed return in the supplied grid"]
    else:
        result["narang_time_decay_assessment"] = "NO_DECAY_OBSERVED"
        result["reasons"] = ["the supplied delayed-entry replay does not show endpoint return decay"]
    return result
