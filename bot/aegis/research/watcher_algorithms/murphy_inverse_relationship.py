"""Cross-asset inverse-relationship confirmation from Murphy's text."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "murphy_inverse_relationship"
SOURCES = ("Trading with Intermarket Analysis",)
KEYS = (
    "murphy_lead_symbol",
    "murphy_target_symbol",
    "murphy_lead_direction",
    "murphy_target_direction",
    "murphy_expected_relationship",
    "murphy_rolling_correlation",
    "murphy_relationship_status",
    "murphy_observation_n",
    "murphy_data_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("cross asset" in label or "synchronized" in label or "timestamped" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "murphy_data_provenance")):
        missing.append("murphy_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = True
    lead = normalized_status(first(state, "murphy_lead_direction")).upper()
    target = normalized_status(first(state, "murphy_target_direction")).upper()
    relationship = normalized_status(first(state, "murphy_expected_relationship"))
    correlation = number(first(state, "murphy_rolling_correlation"))
    observations = number(first(state, "murphy_observation_n"))
    if (
        not isinstance(first(state, "murphy_lead_symbol"), str)
        or not isinstance(first(state, "murphy_target_symbol"), str)
        or lead not in {"UP", "DOWN"}
        or target not in {"UP", "DOWN"}
        or correlation is None
        or not -1 <= correlation <= 1
        or observations is None
        or observations <= 0
        or relationship not in {"inverse", "negative"}
        or not explicitly_validated(first(state, "murphy_relationship_status"), accepted=("validated", "inverse"))
    ):
        result["murphy_intermarket_assessment"] = "UNKNOWN"
        result["reasons"] = ["inverse confirmation requires validated relationship, directions, and observations"]
        return result
    if correlation >= 0 or lead == target:
        result["murphy_intermarket_assessment"] = "RELATIONSHIP_WEAK"
        result["reasons"] = ["the observed pair does not currently show the expected inverse movement"]
        return result
    result["murphy_intermarket_assessment"] = "INVERSE_CONFIRMED" if abs(correlation) >= 0.5 else "RELATIONSHIP_WEAK"
    if result["murphy_intermarket_assessment"] != "INVERSE_CONFIRMED":
        result["reasons"] = ["inverse sign is present but observed correlation strength is weak"]
        return result
    return with_direction(
        result,
        state,
        "BUY" if target == "UP" else "SELL",
        "validated inverse cross-asset relationship confirms the target direction",
    )
