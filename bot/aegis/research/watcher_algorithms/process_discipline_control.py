"""Non-directional process and risk-acceptance diagnostic for the Watcher."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values, with_direction

ALGORITHM_ID = "process_discipline_control"
SOURCES = (
    "Mark Douglas — The Disciplined Trader",
    "Mark Douglas — Trading in the Zone",
    "Jared Tendler — The Mental Game of Trading",
    "Noble DraKoln — Winning the Trading Game",
)
KEYS = (
    "process_rules_defined",
    "process_risk_defined",
    "process_rule_compliant",
    "process_loss_accepted",
    "process_revenge_impulse",
    "process_confirmation_bias",
    "process_emotional_state",
    "process_data_provenance",
)


def _truth(value) -> bool:
    if isinstance(value, bool):
        return value
    return normalized_status(value) in {"true", "yes", "confirmed", "observed", "present", "stable", "calm", "focused", "clear"}


def _provenance_ok(value) -> bool:
    provenance = normalized_status(value)
    return bool(provenance) and not any(
        token in provenance for token in ("synthetic", "fixture", "unknown", "unavailable")
    )


def evaluate(state):
    missing = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "process_data_provenance")):
        missing.append("process_data_provenance")
    found = values(state, *KEYS)
    if missing:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing)))

    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found])
    result["directional_claim"] = False
    reasons = []
    if not _truth(first(state, "process_rules_defined")):
        reasons.append("the governing trading rules were not defined before the decision")
    if not _truth(first(state, "process_risk_defined")):
        reasons.append("risk was not defined before the decision")
    if not _truth(first(state, "process_rule_compliant")):
        reasons.append("the copied decision is not compliant with its governing rules")
    if not _truth(first(state, "process_loss_accepted")):
        reasons.append("the non-guaranteed loss was not explicitly accepted before entry")
    if _truth(first(state, "process_revenge_impulse")):
        reasons.append("revenge-trading impulse is present")
    if _truth(first(state, "process_confirmation_bias")):
        reasons.append("confirmation bias is present")
    if normalized_status(first(state, "process_emotional_state")) not in {"stable", "calm", "focused", "clear"}:
        reasons.append("the recorded decision state is not stable and clear")
    if reasons:
        result["process_assessment"] = "BLOCKED"
        result["reasons"] = reasons
        return with_direction(result, state, None, "process control is a diagnostic and does not create a directional signal")

    result["process_assessment"] = "READY"
    result["reasons"] = ["risk and rules were defined, the decision complied, and no documented process fault was present"]
    return with_direction(result, state, None, "process control is ready but supplies no directional trade signal")
