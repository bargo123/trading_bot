"""Chan's order-dependent CADF cointegration diagnostic."""
from __future__ import annotations

from ._common import absent, base, explicitly_observed, first, number, text, values

ALGORITHM_ID = "chan_cadf_cointegration"
SOURCES = ("Ernest P. Chan — Algorithmic Trading: Winning Strategies and Their Rationale",)
KEYS = (
    "chan_cadf_t_statistic",
    "chan_cadf_critical_value",
    "chan_cadf_hedge_ratio",
    "chan_cadf_independent_order",
    "chan_cadf_data_provenance",
)


def evaluate(state):
    found = values(state, *KEYS)
    statistic = number(first(state, "chan_cadf_t_statistic"))
    critical = number(first(state, "chan_cadf_critical_value"))
    hedge_ratio = number(first(state, "chan_cadf_hedge_ratio"))
    order = text(first(state, "chan_cadf_independent_order"))
    missing = [
        key for key, value in (
            ("chan_cadf_t_statistic", statistic),
            ("chan_cadf_critical_value", critical),
            ("chan_cadf_hedge_ratio", hedge_ratio),
            ("chan_cadf_independent_order", order or None),
        ) if value is None
    ]
    if not explicitly_observed(first(state, "chan_cadf_data_provenance"), accepted=("observed", "measured", "replay")):
        missing.append("chan_cadf_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    result["chan_cadf_order_dependent"] = True
    if critical >= 0 or hedge_ratio == 0:
        result["view"] = "MISSING_DATA"
        result["reasons"] = ["CADF requires a negative critical value and non-zero hedge ratio"]
        return result
    result["chan_cadf_hedge_ratio"] = hedge_ratio
    result["chan_cadf_independent_order"] = order
    if statistic < critical:
        result["chan_cadf_assessment"] = "COINTEGRATION_SUPPORTED"
        result["reasons"] = ["the order-specific CADF statistic exceeds the negative critical threshold"]
    else:
        result["chan_cadf_assessment"] = "COINTEGRATION_NOT_REJECTED"
        result["reasons"] = ["the order-specific CADF unit-root null was not rejected"]
    return result

