"""Probability/risk-acceptance diagnostic from Douglas's trading psychology books."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "douglas_probability_edge"
SOURCES = ("Mark Douglas — The Disciplined Trader", "Mark Douglas — Trading in the Zone")
KEYS = (
    "douglas_edge_defined",
    "douglas_edge_p_win",
    "douglas_edge_sample_n",
    "douglas_outcomes_independent",
    "douglas_risk_accepted",
    "douglas_data_provenance",
)


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "present"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable")
    ) and any(token in label for token in ("observed", "timestamped", "journal"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "douglas_data_provenance")):
        missing.append("douglas_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    probability = number(first(state, "douglas_edge_p_win"))
    sample_n = number(first(state, "douglas_edge_sample_n"))
    result["douglas_edge_probability"] = probability
    if probability is None or not 0 <= probability <= 1 or sample_n is None or sample_n <= 0:
        result["douglas_edge_assessment"] = "INVALID_PROBABILITY"
        result["reasons"] = ["the edge probability and sample must be finite and bounded"]
    elif not _truth(first(state, "douglas_edge_defined")):
        result["douglas_edge_assessment"] = "EDGE_NOT_DEFINED"
        result["reasons"] = ["a probability without a defined repeatable edge is not a trading edge"]
    elif not _truth(first(state, "douglas_outcomes_independent")):
        result["douglas_edge_assessment"] = "DEPENDENCE_UNRESOLVED"
        result["reasons"] = ["each outcome cannot be treated as an independent edge trial yet"]
    elif not _truth(first(state, "douglas_risk_accepted")):
        result["douglas_edge_assessment"] = "RISK_NOT_ACCEPTED"
        result["reasons"] = ["probability does not remove the need to define and accept the trade risk"]
    elif probability > 0.5:
        result["douglas_edge_assessment"] = "PROBABILISTIC_EDGE"
        result["reasons"] = ["the measured edge favors one outcome without requiring a 95 percent threshold"]
    else:
        result["douglas_edge_assessment"] = "NO_EDGE_OBSERVED"
        result["reasons"] = ["the measured probability does not currently favor the proposed outcome"]
    result["douglas_edge_sample_n"] = sample_n
    return result

