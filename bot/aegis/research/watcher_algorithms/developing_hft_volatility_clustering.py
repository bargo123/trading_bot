"""Volatility-clustering context from observed tick-return sequences."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, number, values

ALGORITHM_ID = "developing_hft_volatility_clustering"
SOURCES = ("Developing High-Frequency Trading Systems",)
KEYS = (
    "developing_hft_abs_return_current",
    "developing_hft_abs_return_prior",
    "developing_hft_volatility_cluster_state",
    "developing_hft_volatility_observation_n",
    "developing_hft_volatility_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return any(token in label for token in ("raw tick", "observed tick", "tick return", "observed return"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "developing_hft_volatility_provenance")):
        missing.append("developing_hft_volatility_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    current = number(first(state, "developing_hft_abs_return_current"))
    prior = number(first(state, "developing_hft_abs_return_prior"))
    observations = number(first(state, "developing_hft_volatility_observation_n"))
    state_label = normalized_status(first(state, "developing_hft_volatility_cluster_state"))
    if None in {current, prior, observations} or current < 0 or prior < 0 or observations <= 1:
        result["developing_hft_volatility_assessment"] = "UNKNOWN"
        result["developing_hft_tail_risk_warning"] = True
        result["reasons"] = ["volatility clustering requires finite non-negative returns and observations"]
        return result
    if state_label in {"high cluster", "clustered high", "high volatility cluster"} and current >= prior:
        assessment = "HIGH_CLUSTER"
        tail_warning = True
    elif state_label in {"quiet", "low cluster", "clustered low", "low volatility cluster"} and current < prior:
        assessment = "QUIET"
        tail_warning = False
    else:
        assessment = "UNKNOWN"
        tail_warning = True
    result["developing_hft_volatility_assessment"] = assessment
    result["developing_hft_tail_risk_warning"] = tail_warning
    result["reasons"] = [
        "volatility clustering changes tail-risk context; it is not a directional signal"
    ]
    return result
