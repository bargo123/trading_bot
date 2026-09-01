"""Stationary pair-dislocation perspective from Irene Aldridge's HFT text."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "aldridge_pair_dislocation"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = (
    "aldridge_pair_spread_zscore",
    "aldridge_pair_entry_zscore",
    "aldridge_pair_stationarity",
    "aldridge_pair_signal",
    "aldridge_pair_data_provenance",
)


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "aldridge_pair_data_provenance")):
        missing.append("aldridge_pair_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    zscore = number(first(state, "aldridge_pair_spread_zscore"))
    entry_zscore = number(first(state, "aldridge_pair_entry_zscore"))
    signal = normalized_status(first(state, "aldridge_pair_signal")).upper()
    if zscore is None or entry_zscore is None or entry_zscore <= 0.0 or signal not in {"BUY", "SELL"}:
        result["reasons"] = ["pair dislocation needs finite entry threshold, spread z-score, and explicit leg direction"]
        return result
    if not explicitly_validated(first(state, "aldridge_pair_stationarity"), accepted=("validated", "stationary", "stationarity")):
        result["reasons"] = ["the pair spread has not been validated as stationary"]
        return result
    if abs(zscore) < entry_zscore:
        result["reasons"] = ["the pair spread has not reached its specified dislocation threshold"]
        return result
    expected_signal = "SELL" if zscore > 0.0 else "BUY" if zscore < 0.0 else None
    if signal != expected_signal:
        result["reasons"] = ["the requested leg direction does not match the rich/cheap pair dislocation"]
        return result
    result.update({"aldridge_pair_zscore": zscore, "aldridge_pair_dislocation_confirmed": True})
    return with_direction(result, state, signal, "validated stationary spread dislocation supplies the recorded mean-reversion leg")
