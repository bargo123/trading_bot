"""Narang's parameter-plateau robustness check (Inside the Black Box, ch. 9)."""
from __future__ import annotations

from collections.abc import Sequence

from ._common import absent, base, explicitly_observed, first, number, values


ALGORITHM_ID = "narang_parameter_robustness"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "narang_parameter_grid",
    "narang_parameter_expectancies",
    "narang_parameter_neighbor_tolerance",
    "narang_parameter_data_provenance",
)


def _series(value, *, minimum=3):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None
    result = [number(item) for item in value]
    return result if len(result) >= minimum and all(item is not None for item in result) else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_parameter_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(provenance, accepted=("observed", "measured", "historical", "replay")):
        missing.append("narang_parameter_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    grid = _series(first(state, "narang_parameter_grid"))
    expectancies = _series(first(state, "narang_parameter_expectancies"))
    tolerance = number(first(state, "narang_parameter_neighbor_tolerance"))
    if grid is None or expectancies is None or len(grid) != len(expectancies) or tolerance is None or not 0.0 <= tolerance < 1.0:
        result["narang_parameter_assessment"] = "INVALID_PARAMETER_SWEEP"
        result["reasons"] = ["parameter values, expectancies, and relative-neighbor tolerance must be finite and aligned"]
        return result
    pairs = sorted(zip(grid, expectancies), key=lambda item: item[0])
    if len({parameter for parameter, _ in pairs}) != len(pairs):
        result["narang_parameter_assessment"] = "INVALID_PARAMETER_SWEEP"
        result["reasons"] = ["parameter grid must contain unique values"]
        return result

    best_index, (best_parameter, best_expectancy) = max(
        enumerate(pairs), key=lambda item: item[1][1]
    )
    result.update({
        "narang_robust_parameter": best_parameter,
        "narang_best_parameter_expectancy": best_expectancy,
        "narang_parameter_grid_size": len(pairs),
        "narang_parameter_neighbor_tolerance": tolerance,
        "directional_claim": False,
    })
    if best_expectancy <= 0.0:
        result["narang_parameter_assessment"] = "NO_POSITIVE_PARAMETER_RESULT"
        result["reasons"] = ["the best observed parameter result is not positive"]
        return result

    floor = best_expectancy * (1.0 - tolerance)
    left_ok = best_index > 0 and pairs[best_index - 1][1] >= floor
    right_ok = best_index < len(pairs) - 1 and pairs[best_index + 1][1] >= floor
    result["narang_parameter_neighbor_floor"] = floor
    result["narang_robust_neighbor_count"] = int(left_ok) + int(right_ok)
    if left_ok and right_ok:
        result["narang_parameter_assessment"] = "ROBUST_PLATEAU"
        result["reasons"] = ["the best point has acceptable observed neighbors on both sides"]
    else:
        result["narang_parameter_assessment"] = "SINGLE_PEAK_WARNING"
        result["reasons"] = ["the best point lacks a two-sided neighboring performance plateau"]
    return result
