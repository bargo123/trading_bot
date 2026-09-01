"""Private helpers for Aldridge cost-aware arbitrage perspectives."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, explicitly_validated, first, normalized_status, number, values, with_direction
from ._deprado_common import provenance_ok


def dislocation(
    state,
    *,
    algorithm_id: str,
    keys: tuple[str, ...],
    residual_key: str,
    threshold_key: str,
    edge_key: str,
    direction_key: str,
    provenance_key: str,
    synchronization_key: str | None = None,
    validation_key: str | None = None,
    output_prefix: str,
    warning: str,
):
    found = values(state, *keys)
    missing = [key for key in keys if first(state, key) is None]
    provenance = first(state, provenance_key)
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append(provenance_key)
    if missing:
        return absent(algorithm_id, state, ("Irene Aldridge — High-Frequency Trading",), keys, list(dict.fromkeys(missing)))

    result = base(algorithm_id, state, ("Irene Aldridge — High-Frequency Trading",), [key for key, _ in found])
    residual = number(first(state, residual_key))
    threshold = number(first(state, threshold_key))
    edge = number(first(state, edge_key))
    direction = normalized_status(first(state, direction_key)).upper()
    if residual is None or threshold is None or edge is None or threshold <= 0 or direction not in {"BUY", "SELL"}:
        result["reasons"] = ["arbitrage requires finite dislocation, positive threshold, edge, and explicit direction"]
        return result
    if synchronization_key is not None and first(state, synchronization_key) is not True:
        result["reasons"] = ["leg quotes are not explicitly synchronized"]
        return result
    if validation_key is not None and not explicitly_validated(first(state, validation_key), accepted=("validated", "stationary", "cointegrated")):
        result["reasons"] = ["the cross-asset relationship is not explicitly validated"]
        return result
    if abs(residual) < threshold:
        result["reasons"] = ["the observed dislocation has not reached its specified threshold"]
        return result
    expected_direction = "BUY" if residual < 0 else "SELL"
    if direction != expected_direction:
        result["reasons"] = ["the requested direction does not match the sign of the observed dislocation"]
        return result
    if edge <= 0:
        result["reasons"] = ["the observed arbitrage edge is not positive after execution costs"]
        return result
    result[f"{output_prefix}_residual"] = residual
    result[f"{output_prefix}_net_edge_after_cost"] = edge
    result[f"{output_prefix}_confirmed"] = True
    result["warnings"] = [warning]
    return with_direction(result, state, direction, "source-defined dislocation is aligned and positive after costs")
