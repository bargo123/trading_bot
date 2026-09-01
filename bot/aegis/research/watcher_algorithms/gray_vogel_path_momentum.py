"""Gray and Vogel's continuous-path quantitative momentum perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "gray_vogel_path_momentum"
SOURCES = ("Wesley R. Gray and Jack R. Vogel — Quantitative Momentum",)
KEYS = (
    "gray_formation_return",
    "gray_momentum_decile",
    "gray_positive_return_fraction",
    "gray_negative_return_fraction",
    "gray_formation_lookback_months",
    "gray_skip_recent_period",
    "gray_universe_count",
    "gray_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "gray_data_provenance")):
        missing.append("gray_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    formation_return = number(first(state, "gray_formation_return"))
    decile = number(first(state, "gray_momentum_decile"))
    positive_fraction = number(first(state, "gray_positive_return_fraction"))
    negative_fraction = number(first(state, "gray_negative_return_fraction"))
    lookback = number(first(state, "gray_formation_lookback_months"))
    universe_count = number(first(state, "gray_universe_count"))
    if any(value is None for value in (formation_return, decile, positive_fraction, negative_fraction, lookback, universe_count)):
        result["reasons"] = ["momentum ranking needs finite formation, path, lookback, and universe observations"]
        return result
    if not decile.is_integer() or not 1.0 <= decile <= 10.0:
        result["reasons"] = ["momentum rank must be an observed decile from 1 through 10"]
        return result
    if formation_return == 0.0 or lookback < 12.0 or universe_count <= 0.0:
        result["reasons"] = ["the rule requires a nonzero 12-month formation return and a nonempty universe"]
        return result
    if first(state, "gray_skip_recent_period") is not True:
        result["reasons"] = ["the most recent formation period must be explicitly skipped"]
        return result
    if not 0.0 <= positive_fraction <= 1.0 or not 0.0 <= negative_fraction <= 1.0:
        result["reasons"] = ["positive and negative return fractions must be bounded"]
        return result
    if positive_fraction + negative_fraction > 1.0 + 1e-9:
        result["reasons"] = ["positive and negative return fractions cannot exceed the observed path"]
        return result

    information_discreteness = (1.0 if formation_return > 0.0 else -1.0) * (negative_fraction - positive_fraction)
    result["gray_information_discreteness"] = information_discreteness
    if information_discreteness >= 0.0:
        result["reasons"] = ["the momentum path is not continuous in its observed direction"]
        return result
    signal = "BUY" if decile >= 9.0 else "SELL" if decile <= 2.0 else None
    if signal is None:
        result["reasons"] = ["the observed momentum rank is outside the selected top or bottom deciles"]
        return result
    result.update({"gray_momentum_decile": int(decile), "gray_path_quality": "continuous"})
    return with_direction(result, state, signal, "extreme cross-sectional momentum and a continuous formation path agree")
