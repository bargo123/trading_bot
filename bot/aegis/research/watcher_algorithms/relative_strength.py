"""Relative-strength-versus-benchmark context."""
from __future__ import annotations

from ._common import absent, base, first, number, strings, values, with_direction

ALGORITHM_ID = "relative_strength"
SOURCES = ("John J. Murphy — Technical Analysis of the Financial Markets", "Kathy Lien — Day Trading and Swing Trading the Currency Market")
KEYS = ("relative_strength_ratio", "relative_strength_direction", "relative_strength_benchmark", "relative_strength_as_of")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("as_of_relative_strength",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    ratio = number(first(state, "relative_strength_ratio"))
    direction_text = strings(state, "relative_strength_direction")
    benchmark = first(state, "relative_strength_benchmark")
    as_of = first(state, "relative_strength_as_of")
    if ratio is None or not benchmark or not as_of or ratio <= 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["benchmark_relative_strength_as_of"]
        return result
    if ratio > 1 and "up" in direction_text:
        return with_direction(result, state, "BUY", "instrument is outperforming its recorded benchmark")
    if ratio < 1 and "down" in direction_text:
        return with_direction(result, state, "SELL", "instrument is underperforming its recorded benchmark")
    result["view"] = "WAIT"
    result["reasons"] = ["relative-strength ratio and direction do not establish leadership or weakness"]
    return result
