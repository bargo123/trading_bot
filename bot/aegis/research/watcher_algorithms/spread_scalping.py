"""Cost- and inventory-aware spread-scalping perspective.

The HFT literature describes naive spread capture as vulnerable to inventory
and adverse-selection losses. This Watcher perspective therefore records a
two-sided, closeable, cost-positive state only as research context; it never
authorizes a quote or a directional trade.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "spread_scalping"
SOURCES = (
    "Irene Aldridge — High-Frequency Trading",
    "Maureen O'Hara — Market Microstructure Theory",
    "Barry Johnson — Algorithmic Trading and DMA",
)
KEYS = (
    "spread_scaling_state",
    "spread_scalping_provenance",
    "two_sided_quote",
    "inventory_state",
    "adverse_selection_state",
    "closeability",
    "net_edge",
    "spread_pips",
    "quote_fresh",
    "quote_age_s",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _observed(value) -> bool:
    label = normalized_status(value)
    if not label or any(_has_token(label, marker) for marker in ("unknown", "missing", "unavailable", "synthetic", "proxy", "unverified", "not observed")):
        return False
    return any(_has_token(label, marker) for marker in ("point in time", "quote history", "observed", "measured"))


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("two_sided_cost_and_inventory_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    if not _observed(first(state, "spread_scalping_provenance")):
        result["spread_scalping_assessment"] = "UNKNOWN"
        result["warnings"] = ["spread-scalping inputs lack point-in-time observed provenance"]
        result["reasons"] = ["spread capture cannot be assessed from generic or proxy labels"]
        return result
    if first(state, "two_sided_quote") is not True:
        result["spread_scalping_assessment"] = "NOT_TWO_SIDED"
        result["reasons"] = ["spread capture requires an explicitly observed two-sided quote"]
        return result
    net_edge = number(first(state, "net_edge"))
    if net_edge is None or net_edge <= 0:
        result["spread_scalping_assessment"] = "NEGATIVE_NET_EDGE"
        result["reasons"] = ["spread capture is not positive after the supplied costs"]
        return result
    adverse = normalized_status(first(state, "adverse_selection_state"))
    inventory = normalized_status(first(state, "inventory_state"))
    closeability = normalized_status(first(state, "closeability"))
    if _has_token(adverse, "high") or any(_has_token(inventory, marker) for marker in ("max long", "max short", "blocked", "unsafe")):
        result["spread_scalping_assessment"] = "HIGH_RISK"
        result["warnings"] = ["inventory or adverse-selection risk dominates naive spread capture"]
        result["reasons"] = ["the copied state is not safe for a closeable two-sided spread hypothesis"]
        return result
    if not any(_has_token(adverse, marker) for marker in ("low", "benign", "normal", "safe")) or not any(_has_token(inventory, marker) for marker in ("flat", "within", "controlled")) or not any(_has_token(closeability, marker) for marker in ("observed", "available", "closeable")):
        result["spread_scalping_assessment"] = "UNKNOWN"
        result["reasons"] = ["inventory, adverse-selection, and closeability states are not fully classified"]
        return result
    result["spread_scalping_assessment"] = "CONTROLLED"
    result["reasons"] = ["observed two-sided quotes have controlled inventory/selection risk and positive net edge"]
    return result
