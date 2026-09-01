"""Average-true-range volatility context, kept non-directional."""
from __future__ import annotations

from ._common import base, strings, values

ALGORITHM_ID = "atr_regime"
SOURCES = (
    "John J. Murphy — Technical Analysis of the Financial Markets",
    "Marcel Link — High Probability Trading",
    "Robert Carver — Systematic Trading",
)
KEYS = ("atr_14", "atr_percent", "atr_state", "atr_observation_n")


def evaluate(state):
    found = values(state, *KEYS)
    if not found:
        return base(ALGORITHM_ID, state, SOURCES, KEYS, applicability="MISSING_DATA", view="MISSING_DATA", missing_inputs=("atr_context",))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    classification = strings(state, "atr_state") or "unknown"
    result["atr_classification"] = classification.upper()
    result["directional_claim"] = False
    result["risk_context"] = "avoid_new_entry_if_extreme" if "extreme" in classification else (
        "compressed_range" if "compressed" in classification else "expanding_range" if "expanding" in classification else "observed"
    )
    result["reasons"] = ["ATR describes movement regime and risk geometry; it does not choose BUY or SELL"]
    return result
