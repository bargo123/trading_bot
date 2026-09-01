"""Business-cycle sector-leadership perspective from Murphy's text."""
from __future__ import annotations

from ._common import absent, base, explicitly_validated, first, normalized_status, number, values, with_direction

ALGORITHM_ID = "murphy_sector_rotation"
SOURCES = ("Trading with Intermarket Analysis",)
KEYS = (
    "murphy_business_cycle_phase",
    "murphy_leader_group",
    "murphy_candidate_group",
    "murphy_candidate_direction",
    "murphy_relative_strength",
    "murphy_sector_rotation_status",
    "murphy_sector_observation_n",
    "murphy_sector_data_provenance",
)

LEADERS_BY_PHASE = {
    "early expansion": {"consumer discretionary", "technology", "transportation", "small caps"},
    "late expansion": {"energy"},
    "downturn": {"consumer staples", "health care", "utilities"},
    "contraction": {"consumer staples", "health care", "utilities"},
}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    if not label or any(token in label for token in ("synthetic", "fixture", "unknown", "unavailable", "proxy")):
        return False
    return "observed" in label and ("sector" in label or "returns" in label)


def evaluate(state):
    found = values(state, *KEYS)
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "murphy_sector_data_provenance")):
        missing.append("murphy_sector_data_provenance")
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    phase = normalized_status(first(state, "murphy_business_cycle_phase"))
    leader = normalized_status(first(state, "murphy_leader_group"))
    candidate = normalized_status(first(state, "murphy_candidate_group"))
    direction = normalized_status(first(state, "murphy_candidate_direction")).upper()
    strength = number(first(state, "murphy_relative_strength"))
    observations = number(first(state, "murphy_sector_observation_n"))
    if (
        phase not in LEADERS_BY_PHASE
        or not leader
        or not candidate
        or direction not in {"BUY", "SELL"}
        or strength is None
        or observations is None
        or observations <= 0
        or not explicitly_validated(first(state, "murphy_sector_rotation_status"), accepted=("validated", "sector rotation"))
    ):
        result["murphy_sector_assessment"] = "UNKNOWN"
        result["reasons"] = ["sector rotation requires a validated phase, leadership, and relative-strength observation"]
        return result
    if candidate not in LEADERS_BY_PHASE[phase] or leader != candidate:
        result["murphy_sector_assessment"] = "PHASE_MISMATCH"
        result["reasons"] = ["candidate sector is not the observed leader for the supplied business-cycle phase"]
        return result
    if strength <= 0:
        result["murphy_sector_assessment"] = "NO_RELATIVE_STRENGTH"
        result["reasons"] = ["the candidate sector is not outperforming on the observed relative-strength measure"]
        return result
    result["murphy_sector_assessment"] = "LEADING_SECTOR"
    return with_direction(result, state, direction, "validated business-cycle phase and relative strength identify a sector leader")
