"""Volatility-adjusted stop and size diagnostic from Oreste's money rules."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "oreste_volatility_scaled_risk"
SOURCES = ("Fabio Oreste — Quantum Trading",)
KEYS = (
    "oreste_volatility_regime",
    "oreste_baseline_stop_distance",
    "oreste_current_stop_distance",
    "oreste_position_risk_usd",
    "oreste_max_risk_usd",
    "oreste_position_units",
    "oreste_baseline_units",
    "oreste_volatility_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in label for token in ("observed", "timestamped", "measured"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "oreste_volatility_data_provenance")):
        missing.append("oreste_volatility_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    regime = normalized_status(first(state, "oreste_volatility_regime"))
    baseline_stop = number(first(state, "oreste_baseline_stop_distance"))
    current_stop = number(first(state, "oreste_current_stop_distance"))
    risk = number(first(state, "oreste_position_risk_usd"))
    max_risk = number(first(state, "oreste_max_risk_usd"))
    units = number(first(state, "oreste_position_units"))
    baseline_units = number(first(state, "oreste_baseline_units"))
    if (
        regime not in {"low", "normal", "high", "elevated"}
        or None in {baseline_stop, current_stop, risk, max_risk, units, baseline_units}
        or min(baseline_stop, current_stop, risk, max_risk, units, baseline_units) <= 0
        or risk > max_risk
    ):
        result["oreste_volatility_risk_assessment"] = "RISK_OR_INPUT_INVALID"
        result["reasons"] = ["volatility scaling requires positive distances, units, and risk within the cap"]
        return result
    result["oreste_stop_expanded"] = current_stop > baseline_stop
    result["oreste_units_reduced"] = units < baseline_units
    if regime in {"high", "elevated"} and current_stop < baseline_stop:
        result["oreste_volatility_risk_assessment"] = "STOP_TOO_TIGHT_FOR_VOL"
        result["reasons"] = ["higher observed volatility requires a wider stop or a separately validated model"]
    elif regime in {"high", "elevated"} and not result["oreste_units_reduced"]:
        result["oreste_volatility_risk_assessment"] = "SIZE_REDUCTION_MISSING"
        result["reasons"] = ["the wider high-volatility stop was not paired with lower units"]
    else:
        result["oreste_volatility_risk_assessment"] = "ADJUSTED_WITHIN_RISK"
        result["reasons"] = ["volatility geometry is adjusted while observed per-trade risk stays within the cap"]
    return result

