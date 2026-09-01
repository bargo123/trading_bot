"""Fee/rebate economics perspective for the read-only Watcher.

Rebates can change the break-even probability of a passive order, but cannot
replace a directional forecast or realistic fill model. This module requires
an explicit venue fee schedule and records the economics without authorizing
an order.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "rebate_capture"
SOURCES = (
    "Irene Aldridge — High-Frequency Trading",
    "Barry Johnson — Algorithmic Trading and DMA",
    "David Aronson — Evidence-Based Technical Analysis",
)
KEYS = (
    "rebate_state",
    "rebate_provenance",
    "rebate_per_unit",
    "transaction_cost_per_unit",
    "fill_probability",
    "directional_probability",
    "net_edge_after_cost",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _valid_provenance(value) -> bool:
    label = normalized_status(value)
    if not label or any(_has_token(label, marker) for marker in ("unknown", "missing", "unavailable", "synthetic", "proxy", "unverified")):
        return False
    return any(_has_token(label, marker) for marker in ("venue fee schedule", "measured fee", "observed fee"))


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("venue_fee_schedule_and_fill_economics",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    rebate = number(first(state, "rebate_per_unit"))
    cost = number(first(state, "transaction_cost_per_unit"))
    fill = number(first(state, "fill_probability"))
    directional = number(first(state, "directional_probability"))
    edge = number(first(state, "net_edge_after_cost"))
    if not _valid_provenance(first(state, "rebate_provenance")):
        result["rebate_assessment"] = "UNKNOWN"
        result["warnings"] = ["rebate data is not tied to an observed venue fee schedule"]
        result["reasons"] = ["fee/rebate values cannot be assessed from proxy or missing provenance"]
        return result
    if None in {rebate, cost, fill, directional, edge} or rebate < 0 or cost < 0 or not 0 <= fill <= 1 or not 0 <= directional <= 1:
        result["rebate_assessment"] = "UNKNOWN"
        result["reasons"] = ["rebate, cost, fill, and directional-probability inputs are invalid or incomplete"]
        return result
    if edge <= 0:
        result["rebate_assessment"] = "NEGATIVE_NET_EDGE"
        result["reasons"] = ["rebate does not overcome execution costs and forecast economics"]
        return result
    result["rebate_assessment"] = "MEASURED_RESEARCH_ONLY"
    result["reasons"] = ["measured rebate changes break-even economics but is not an independent trading signal"]
    return result
