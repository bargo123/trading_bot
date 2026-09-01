"""Narang's recent-performance rotation perspective (Inside the Black Box, ch. 3)."""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ._common import absent, base, explicitly_observed, first, number, values

ALGORITHM_ID = "narang_alpha_rotation"
SOURCES = ("Rishi K. Narang — Inside the Black Box",)
KEYS = (
    "narang_factor_recent_performance",
    "narang_rotation_data_provenance",
)


def _performance(value):
    if not isinstance(value, Mapping) or not value:
        return None
    parsed = {}
    for name, observations in value.items():
        if not isinstance(name, str) or not name.strip():
            return None
        if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes, bytearray)):
            return None
        series = [number(item) for item in observations]
        if len(series) < 3 or any(item is None for item in series):
            return None
        parsed[name.strip()] = series
    return parsed if len(parsed) >= 2 else None


def evaluate(state):
    found = values(state, *KEYS)
    provenance = first(state, "narang_rotation_data_provenance")
    missing = [key for key in KEYS if first(state, key) is None]
    if not explicitly_observed(
        provenance,
        accepted=("observed", "measured", "historical", "replay"),
    ):
        missing.append("narang_rotation_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    performance = _performance(first(state, "narang_factor_recent_performance"))
    if performance is None:
        result["narang_rotation_action"] = "INVALID_FACTOR_PERFORMANCE"
        result["reasons"] = [
            "rotation needs at least two named factors with three or more finite observed returns each"
        ]
        return result

    ranking = sorted(
        ((name, sum(series) / len(series), len(series)) for name, series in performance.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    result.update({
        "narang_factor_ranking": ranking,
        "narang_factor_count": len(ranking),
        "narang_rotation_observation_n": {name: count for name, _, count in ranking},
        "directional_claim": False,
    })
    best_name, best_score, _ = ranking[0]
    result["narang_selected_factor"] = best_name
    result["narang_selected_factor_recent_mean"] = best_score
    if best_score <= 0.0:
        result["narang_rotation_action"] = "NO_POSITIVE_RECENT_FACTOR"
        result["reasons"] = ["the strongest observed factor has non-positive recent mean performance"]
        return result
    if len(ranking) > 1 and best_score == ranking[1][1]:
        result["narang_rotation_action"] = "NO_CLEAR_ROTATION_LEADER"
        result["reasons"] = ["the strongest observed factors have equal recent mean performance"]
        return result

    result["narang_rotation_action"] = "ROTATE_TO_RECENT_STRONGEST"
    result["reasons"] = [
        "recent observed factor performance identifies a strongest factor for research weighting"
    ]
    result["warnings"] = [
        "rotation ranks factor performance; it does not prove future returns or select a BUY/SELL direction"
    ]
    return result
