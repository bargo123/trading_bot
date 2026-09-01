"""Tail-loss geometry perspective for the read-only Watcher.

Risk literature treats extreme losses as a separate state variable. This
module records whether supplied tail evidence is controlled, elevated, or
unknown; it never turns a loss statistic into a directional signal or an
execution decision.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "tail_risk"
SOURCES = (
    "Kevin Davey — Building Winning Algorithmic Trading Systems",
    "Robert Carver — Systematic Trading",
    "David Aronson — Evidence-Based Technical Analysis",
    "Marcos Lopez de Prado — Advances in Financial Machine Learning",
    "Van K. Tharp — Trade Your Way to Financial Freedom",
)
KEYS = (
    "tail_risk_state",
    "tail_loss",
    "p95_loss",
    "p99_loss",
    "max_adverse_excursion",
    "loss_quantile_provenance",
    "tail_risk_provenance",
    "risk_budget",
    "expected_loss",
)


def _has_token(value: str, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", value))


def _provenance_is_observed(value) -> bool:
    label = normalized_status(value)
    if not label or any(
        _has_token(label, marker)
        for marker in ("unknown", "missing", "unavailable", "synthetic", "proxy", "unverified", "not observed", "not real")
    ):
        return False
    return any(
        _has_token(label, marker)
        for marker in (
            "walk forward net outcomes",
            "broker confirmed net outcomes",
            "measured net outcomes",
            "observed",
        )
    )


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("tail_loss_or_risk_state",))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    state_label = normalized_status(first(state, "tail_risk_state"))
    numeric_keys = ("tail_loss", "p95_loss", "p99_loss", "max_adverse_excursion", "risk_budget", "expected_loss")
    numeric_values = {key: number(first(state, key)) for key in numeric_keys}
    if numeric_values["risk_budget"] is not None and numeric_values["risk_budget"] < 0:
        result["tail_risk_assessment"] = "UNKNOWN"
        result["reasons"] = ["risk budget cannot be negative"]
        return result
    if any(
        value is not None
        and key in {"tail_loss", "p95_loss", "p99_loss", "max_adverse_excursion", "expected_loss"}
        and value > 0
        for key, value in numeric_values.items()
    ):
        result["tail_risk_assessment"] = "UNKNOWN"
        result["reasons"] = ["loss and adverse-excursion measurements must not be positive"]
        return result
    if not state_label:
        result["tail_risk_assessment"] = "UNKNOWN"
        result["reasons"] = ["numeric tail measurements require an explicit classification threshold"]
        return result
    if not _provenance_is_observed(first(state, "tail_risk_provenance", "loss_quantile_provenance")):
        result["tail_risk_assessment"] = "UNKNOWN"
        result["warnings"] = ["tail-risk provenance is missing, synthetic, proxy, or unverified"]
        result["reasons"] = ["tail classification is not supported by observed net-outcome evidence"]
        return result

    high = any(_has_token(state_label, marker) for marker in ("high", "unbounded", "catastrophic", "heavy", "unsafe", "tail"))
    low = any(_has_token(state_label, marker) for marker in ("controlled", "bounded", "acceptable", "contained", "stable"))
    if high and not low:
        result["tail_risk_assessment"] = "HIGH"
        result["warnings"] = ["observed tail-loss geometry is elevated"]
        result["reasons"] = ["walk-forward net outcomes classify tail risk as elevated"]
    elif low and not high:
        result["tail_risk_assessment"] = "CONTROLLED"
        result["reasons"] = ["walk-forward net outcomes classify tail risk as controlled"]
    else:
        result["tail_risk_assessment"] = "UNKNOWN"
        result["reasons"] = ["tail-risk labels are absent or conflicting"]
    return result
