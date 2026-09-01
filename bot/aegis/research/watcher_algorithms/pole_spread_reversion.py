"""Andrew Pole's calibrated pair-spread reversion rule."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "pole_spread_reversion"
SOURCES = ("Andrew Pole — Statistical Arbitrage",)
KEYS = (
    "pole_spread_zscore",
    "pole_entry_zscore_threshold",
    "pole_exit_zscore_target",
    "pole_stationarity",
    "pole_pair_correlation",
    "pole_min_pair_correlation",
    "pole_calibration_window",
    "pole_pair_id",
    "pole_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "pole_data_provenance")):
        missing.append("pole_data_provenance")
    missing = list(dict.fromkeys(missing))
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    zscore = number(first(state, "pole_spread_zscore"))
    entry_threshold = number(first(state, "pole_entry_zscore_threshold"))
    exit_target = number(first(state, "pole_exit_zscore_target"))
    correlation = number(first(state, "pole_pair_correlation"))
    minimum_correlation = number(first(state, "pole_min_pair_correlation"))
    calibration_window = number(first(state, "pole_calibration_window"))
    if any(value is None for value in (zscore, entry_threshold, exit_target, correlation, minimum_correlation, calibration_window)):
        result["reasons"] = ["spread reversion needs finite z-score, calibration, correlation, and exit observations"]
        return result
    if entry_threshold <= 0.0 or minimum_correlation <= 0.0 or minimum_correlation > 1.0:
        result["reasons"] = ["entry and correlation thresholds must be positive and bounded"]
        return result
    if not 0.0 <= correlation <= 1.0 or correlation < minimum_correlation:
        result["reasons"] = ["the pair correlation is below its point-in-time selection threshold"]
        return result
    if calibration_window <= 0.0:
        result["reasons"] = ["the spread calibration window must be positive"]
        return result
    if not explicitly_validated(first(state, "pole_stationarity"), accepted=("validated", "stationary", "stationarity")):
        result["reasons"] = ["the pair spread has no explicit validated stationarity observation"]
        return result
    if abs(exit_target) >= entry_threshold:
        result["reasons"] = ["the reversion target must lie inside the entry band"]
        return result

    signal = "BUY" if zscore <= -entry_threshold else "SELL" if zscore >= entry_threshold else None
    if signal is None:
        result["reasons"] = ["the calibrated spread is inside its entry band"]
        return result
    result.update(
        {
            "pole_spread_zscore": zscore,
            "pole_reversion_target_zscore": exit_target,
            "pole_pair_correlation": correlation,
            "pole_reversion_confirmed": True,
        }
    )
    return with_direction(result, state, signal, "validated correlated spread is beyond its calibrated reversion entry limit")
