"""Aldridge same-issuer dual-class share dislocation perspective."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, normalized_status, number, values, with_direction
from ._deprado_common import provenance_ok

ALGORITHM_ID = "aldridge_dual_class_arbitrage"
SOURCES = ("Irene Aldridge — High-Frequency Trading",)
KEYS = ("aldridge_dual_class_premium", "aldridge_dual_class_threshold", "aldridge_dual_class_net_edge_after_cost", "aldridge_dual_class_direction", "aldridge_dual_class_liquidity_ratio", "aldridge_dual_class_data_provenance")


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    provenance = first(state, "aldridge_dual_class_data_provenance")
    if not explicitly_observed(provenance, accepted=("observed", "measured", "replay")) or not provenance_ok(provenance):
        missing.append("aldridge_dual_class_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    premium = number(first(state, "aldridge_dual_class_premium"))
    threshold = number(first(state, "aldridge_dual_class_threshold"))
    edge = number(first(state, "aldridge_dual_class_net_edge_after_cost"))
    liquidity = number(first(state, "aldridge_dual_class_liquidity_ratio"))
    direction = normalized_status(first(state, "aldridge_dual_class_direction")).upper()
    if None in {premium, threshold, edge, liquidity} or threshold <= 0 or liquidity <= 0 or direction not in {"BUY", "SELL"}:
        result["reasons"] = ["dual-class arbitrage requires finite premium, threshold, liquidity, edge, and direction"]
        return result
    if abs(premium) < threshold:
        result["reasons"] = ["same-issuer premium has not reached its specified dislocation threshold"]
        return result
    expected_direction = "BUY" if premium < 0 else "SELL"
    if direction != expected_direction:
        result["reasons"] = ["dual-class direction does not match the observed premium sign"]
        return result
    if edge <= 0:
        result["reasons"] = ["dual-class edge is not positive after execution costs"]
        return result
    result.update({"aldridge_dual_class_premium": premium, "aldridge_dual_class_liquidity_ratio": liquidity, "aldridge_dual_class_confirmed": True})
    return with_direction(result, state, direction, "same-issuer dislocation has sufficient observed liquidity and positive net edge")
