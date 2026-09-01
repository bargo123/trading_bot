"""Al Brooks' shrinking-stairs warning for waning breakout momentum."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values

ALGORITHM_ID = "brooks_shrinking_stairs"
SOURCES = ("Al Brooks — Trading Price Action Trading Ranges",)
KEYS = (
    "brooks_stairs_direction",
    "brooks_stairs_breakout_sizes",
    "brooks_stairs_data_provenance",
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
    if not _brooks_provenance_ok(first(state, "brooks_stairs_data_provenance")):
        missing.append("brooks_stairs_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    direction = normalized_status(first(state, "brooks_stairs_direction"))
    raw_sizes = first(state, "brooks_stairs_breakout_sizes")
    result["view"] = "WAIT"
    if direction not in {"up", "down"} or isinstance(raw_sizes, (str, bytes, bytearray)) or not isinstance(raw_sizes, Sequence):
        result["brooks_stairs_assessment"] = "STAIRS_INPUT_INVALID"
        result["reasons"] = ["the stairs need an up/down direction and an ordered numeric breakout-size sequence"]
        return result
    sizes = [number(value) for value in raw_sizes]
    if len(sizes) < 3 or any(value is None or value <= 0 for value in sizes):
        result["brooks_stairs_assessment"] = "STAIRS_INPUT_INVALID"
        result["reasons"] = ["the source shrinking-stairs pattern needs at least three positive breakout sizes"]
        return result

    result["brooks_stairs_breakout_sizes"] = sizes
    result["brooks_stairs_direction"] = direction
    if all(current < previous for previous, current in zip(sizes, sizes[1:])):
        result["brooks_stairs_assessment"] = "SHRINKING_STAIRS_WANING_MOMENTUM"
        result["warnings"] = [
            "successive breakouts are shrinking, which the source treats as waning trend momentum rather than a fresh entry signal"
        ]
    else:
        result["brooks_stairs_assessment"] = "NO_SHRINKING_STAIRS"
        result["reasons"] = ["successive breakout sizes are not strictly decreasing"]
    return result
