"""Lead/lag turn confirmation from Murphy's intermarket principles."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "murphy_lead_lag_confirmation"
SOURCES = ("Trading with Intermarket Analysis",)
KEYS = (
    "murphy_lead_symbol",
    "murphy_target_symbol",
    "murphy_lead_direction",
    "murphy_target_direction",
    "murphy_expected_relationship",
    "murphy_lead_changed_first",
    "murphy_relationship_status",
    "murphy_observation_n",
    "murphy_lead_lag_provenance",
)


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("turn" in label or "lead" in label or "cross asset" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "murphy_lead_lag_provenance")):
        missing.append("murphy_lead_lag_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = True
    lead = normalized_status(first(state, "murphy_lead_direction")).upper()
    target = normalized_status(first(state, "murphy_target_direction")).upper()
    relationship = normalized_status(first(state, "murphy_expected_relationship"))
    observations = number(first(state, "murphy_observation_n"))
    if (
        lead not in {"UP", "DOWN"}
        or target not in {"UP", "DOWN"}
        or relationship not in {"inverse", "direct"}
        or observations is None
        or observations <= 0
        or not explicitly_validated(first(state, "murphy_relationship_status"), accepted=("validated", "lead lag"))
    ):
        result["murphy_lead_lag_assessment"] = "UNKNOWN"
        result["reasons"] = ["lead/lag confirmation requires validated relationship and directional observations"]
        return result
    if first(state, "murphy_lead_changed_first") is not True:
        result["murphy_lead_lag_assessment"] = "LEAD_NOT_PROVEN"
        result["reasons"] = ["the lead market did not demonstrably turn before the target market"]
        return result
    consistent = target != lead if relationship == "inverse" else target == lead
    if not consistent:
        result["murphy_lead_lag_assessment"] = "RELATIONSHIP_CONFLICT"
        result["reasons"] = ["target direction conflicts with the observed relationship type"]
        return result
    result["murphy_lead_lag_assessment"] = "LEAD_CONFIRMED"
    return with_direction(
        result,
        state,
        "BUY" if target == "UP" else "SELL",
        "the validated lead market turned before the target in the expected direction",
    )
