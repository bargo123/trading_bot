"""Multi-venue latency-discrepancy perspective for the read-only Watcher.

Latency arbitrage depends on the same instrument being observed at multiple
venues with synchronized timestamps and enough measured latency to execute
before the discrepancy disappears. A single MT5 venue cannot establish this
edge; the evaluator records that limitation explicitly and never trades it.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "latency_arbitrage"
SOURCES = (
    "Irene Aldridge — High-Frequency Trading",
    "Barry Johnson — Algorithmic Trading and DMA",
    "Jean-Philippe Bouchaud et al. — Trades, Quotes and Prices",
)
KEYS = (
    "latency_state",
    "venue_count",
    "venue_price_discrepancy",
    "latency_budget_ms",
    "latency_observed_ms",
    "net_edge_after_cost",
    "latency_provenance",
    "venue_timestamps_synchronized",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _observed(value) -> bool:
    label = normalized_status(value)
    if not label or any(_has_token(label, marker) for marker in ("unknown", "missing", "unavailable", "synthetic", "proxy", "unverified", "not observed")):
        return False
    return any(_has_token(label, marker) for marker in ("timestamped", "multi venue", "observed", "measured"))


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("synchronized_multi_venue_quotes",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    venue_count = number(first(state, "venue_count"))
    if venue_count is None or venue_count < 2:
        result["latency_assessment"] = "NOT_APPLICABLE"
        result["warnings"] = ["latency arbitrage requires at least two observed venues for the same instrument"]
        result["reasons"] = ["the copied MT5 state does not establish a multi-venue discrepancy"]
        return result
    discrepancy = number(first(state, "venue_price_discrepancy"))
    budget = number(first(state, "latency_budget_ms"))
    observed = number(first(state, "latency_observed_ms"))
    edge = number(first(state, "net_edge_after_cost"))
    if discrepancy is None or discrepancy <= 0 or budget is None or budget <= 0 or observed is None or observed < 0 or edge is None:
        result["latency_assessment"] = "UNKNOWN"
        result["reasons"] = ["latency discrepancy, execution budget, and net edge are not valid"]
        return result
    if not _observed(first(state, "latency_provenance")) or first(state, "venue_timestamps_synchronized") is not True:
        result["latency_assessment"] = "UNKNOWN"
        result["warnings"] = ["venue quotes are not proven synchronized and observed"]
        result["reasons"] = ["latency edge requires synchronized point-in-time venue observations"]
        return result
    if observed > budget or edge <= 0:
        result["latency_assessment"] = "NEGATIVE_EXECUTABLE_EDGE"
        result["reasons"] = ["measured latency or after-cost economics cannot capture the discrepancy"]
        return result
    result["latency_assessment"] = "MEASURED_RESEARCH_ONLY"
    result["reasons"] = ["multi-venue discrepancy is measurable but this Watcher has no execution authority"]
    return result
