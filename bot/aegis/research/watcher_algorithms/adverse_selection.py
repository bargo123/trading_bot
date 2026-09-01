"""Adverse-selection warning perspective for the read-only Watcher.

The microstructure literature treats informed/toxic flow as an execution
hazard, not as a directional entry signal.  This evaluator therefore only
classifies the copied state and never emits BUY or SELL authority.
"""
from __future__ import annotations

import re

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "adverse_selection"
SOURCES = (
    "Marcos Lopez de Prado — Advances in Financial Machine Learning",
    "Irene Aldridge — High-Frequency Trading",
    "Barry Johnson — Algorithmic Trading and DMA",
    "Jean-Philippe Bouchaud — Trades, Quotes and Prices",
)
KEYS = (
    "adverse_selection_state",
    "adverse_selection_score",
    "quote_toxicity",
    "informed_flow",
    "order_flow_toxicity",
    "adverse_selection_provenance",
    "spread_pips",
    "quote_age_s",
    "quote_fresh",
)


def _negative_label(value) -> bool:
    label = normalized_status(value)
    return any(marker in label for marker in ("not ", "unknown", "missing", "unavailable", "invalid"))


def _has_token(value, token: str) -> bool:
    return bool(re.search(r"(?<![a-z])" + re.escape(token) + r"(?![a-z])", normalized_status(value)))


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, ("adverse_selection_evidence",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    state_label = normalized_status(first(state, "adverse_selection_state", "informed_flow", "order_flow_toxicity"))
    score = number(first(state, "adverse_selection_score", "quote_toxicity"))
    if _negative_label(state_label):
        result["adverse_selection_assessment"] = "UNKNOWN"
        result["reasons"] = ["adverse-selection state is negated or unavailable"]
        return result

    high = any(_has_token(state_label, token) for token in ("high", "toxic", "informed", "adverse", "unsafe"))
    low = any(_has_token(state_label, token) for token in ("low", "benign", "normal", "safe"))
    if score is not None and not 0.0 <= score <= 1.0:
        result["adverse_selection_assessment"] = "UNKNOWN"
        result["reasons"] = ["adverse-selection score is outside the [0, 1] range"]
        return result
    if score is not None:
        high = high or score > 0.5
        low = low or score <= 0.5
    if not high and not low:
        result["adverse_selection_assessment"] = "UNKNOWN"
        result["reasons"] = ["adverse-selection direction is not classified"]
        return result
    quote_age = number(first(state, "quote_age_s"))
    if first(state, "quote_fresh") is not True or quote_age is None or quote_age > 5:
        result["adverse_selection_assessment"] = "UNKNOWN"
        result["warnings"] = ["quote freshness is insufficient to classify current selection risk"]
        result["reasons"] = ["current quote is stale or explicitly not fresh"]
        return result
    result["adverse_selection_assessment"] = "HIGH" if high and not low else "LOW" if low and not high else "UNKNOWN"
    if result["adverse_selection_assessment"] == "HIGH":
        result["warnings"] = ["avoid entering against potentially informed or toxic flow"]
        result["reasons"] = ["point-in-time flow evidence indicates elevated adverse-selection risk"]
    elif result["adverse_selection_assessment"] == "LOW":
        result["reasons"] = ["point-in-time flow evidence does not indicate elevated adverse-selection risk"]
    else:
        result["reasons"] = ["adverse-selection labels conflict"]
    return result
