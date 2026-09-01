"""Cost-aware short-lived pair-dislocation perspective from the HFT text."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "developing_hft_stat_arb_dislocation"
SOURCES = ("Developing High-Frequency Trading Systems",)
KEYS = (
    "developing_hft_pair_id",
    "developing_hft_pair_dislocation",
    "developing_hft_pair_direction",
    "developing_hft_pair_relationship_status",
    "developing_hft_pair_observation_n",
    "developing_hft_pair_net_edge_after_cost",
    "developing_hft_pair_quotes_synchronized",
    "developing_hft_pair_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return any(token in label for token in ("observed", "synchronized", "timestamped", "live quote"))


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "developing_hft_pair_data_provenance")):
        missing.append("developing_hft_pair_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = True
    pair = first(state, "developing_hft_pair_id")
    dislocation = number(first(state, "developing_hft_pair_dislocation"))
    observations = number(first(state, "developing_hft_pair_observation_n"))
    edge = number(first(state, "developing_hft_pair_net_edge_after_cost"))
    direction = normalized_status(first(state, "developing_hft_pair_direction")).upper()
    relationship = first(state, "developing_hft_pair_relationship_status")
    if (
        not isinstance(pair, str)
        or not pair.strip()
        or None in {dislocation, observations, edge}
        or dislocation <= 0
        or observations <= 0
        or not explicitly_validated(relationship, accepted=("validated", "stationary", "cointegrated"))
        or first(state, "developing_hft_pair_quotes_synchronized") is not True
    ):
        result["developing_hft_stat_arb_assessment"] = "UNVALIDATED"
        result["reasons"] = ["pair dislocation requires validated relationship, synchronized quotes, and observations"]
        return result
    result["developing_hft_pair_id"] = pair
    if edge <= 0:
        result["developing_hft_stat_arb_assessment"] = "NEGATIVE_NET_EDGE"
        result["reasons"] = ["the observed pair discrepancy does not remain positive after execution costs"]
        return result
    if direction not in {"BUY", "SELL"}:
        result["developing_hft_stat_arb_assessment"] = "UNKNOWN_DIRECTION"
        result["reasons"] = ["pair dislocation has no unambiguous executable direction"]
        return result
    result["developing_hft_stat_arb_assessment"] = "POSITIVE_NET_EDGE"
    return with_direction(result, state, direction, "validated short-lived pair dislocation remains positive after costs")
