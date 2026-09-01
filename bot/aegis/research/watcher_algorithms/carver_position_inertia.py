"""Carver's position-inertia rule as a read-only turnover diagnostic."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, side, values, with_direction

ALGORITHM_ID = "carver_position_inertia"
SOURCES = ("Robert Carver — Systematic Trading",)
KEYS = (
    "carver_current_position",
    "carver_rounded_target_position",
    "carver_position_inertia_fraction",
    "carver_position_data_provenance",
)


def _observed(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")
    ) and any(token in provenance for token in ("observed", "historical", "live", "broker"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _observed(first(state, "carver_position_data_provenance")):
        missing.append("carver_position_data_provenance")
    missing = list(dict.fromkeys(missing))
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, missing)

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    current = number(first(state, "carver_current_position"))
    target = number(first(state, "carver_rounded_target_position"))
    inertia = number(first(state, "carver_position_inertia_fraction"))
    if current is None or target is None or inertia is None or inertia < 0:
        result["view"] = "MISSING_DATA"
        result["missing_inputs"] = ["finite_position_and_inertia_fraction"]
        return result
    if not float(target).is_integer():
        result["view"] = "WAIT"
        result["carver_inertia_action"] = "TARGET_NOT_ROUNDED"
        result["reasons"] = ["position inertia is defined against a rounded target position"]
        return result

    delta = abs(target - current)
    threshold = inertia * max(abs(target), 1.0)
    result.update({
        "carver_position_delta": delta,
        "carver_inertia_threshold": threshold,
        "carver_inertia_fraction": inertia,
        "directional_claim": True,
    })
    if delta <= threshold:
        result["view"] = "WAIT"
        result["carver_inertia_action"] = "POSITION_INERTIA_HOLD"
        result["reasons"] = ["target remains within the configured position-inertia band"]
        return result

    signal = "BUY" if target > current else "SELL" if target < current else None
    result["carver_inertia_action"] = "REBALANCE_REQUIRED"
    return with_direction(result, state, signal, "target is outside the position-inertia band")
