"""Three-pillar trading-plan diagnostic from Winning the Trading Game."""
from __future__ import annotations

from ._common import absent, base, first, normalized_status, values

ALGORITHM_ID = "drakoln_plan_integrity"
SOURCES = ("Noble DraKoln — Winning the Trading Game",)
PLAN_KEYS = (
    "drakoln_money_management_defined",
    "drakoln_technical_method_defined",
    "drakoln_risk_management_defined",
    "drakoln_trade_plan_defined",
    "drakoln_entry_rules_defined",
    "drakoln_exit_rules_defined",
    "drakoln_risk_reward_defined",
    "drakoln_losing_streak_plan_defined",
    "drakoln_winning_streak_plan_defined",
)
KEYS = (*PLAN_KEYS, "drakoln_data_provenance")


def _truth(value) -> bool:
    return value is True or normalized_status(value) in {"true", "yes", "confirmed", "defined", "present"}


def _provenance_ok(value) -> bool:
    label = normalized_status(value)
    return bool(label) and not any(
        token in label for token in ("synthetic", "fixture", "unknown", "unavailable")
    ) and any(token in label for token in ("observed", "timestamped", "journal"))


def evaluate(state):
    found = values(state, *KEYS)
    missing_evidence = [key for key in KEYS if first(state, key) is None]
    if not _provenance_ok(first(state, "drakoln_data_provenance")):
        missing_evidence.append("drakoln_data_provenance")
    if missing_evidence:
        return absent(ALGORITHM_ID, state, SOURCES, KEYS, list(dict.fromkeys(missing_evidence)))
    result = base(ALGORITHM_ID, state, SOURCES, [key for key, _ in found], view="WAIT")
    result["directional_claim"] = False
    incomplete = [key for key in PLAN_KEYS if not _truth(first(state, key))]
    result["missing_plan_elements"] = incomplete
    if incomplete:
        result["drakoln_plan_assessment"] = "PLAN_INCOMPLETE"
        result["reasons"] = ["the trading plan is missing one or more money, technical, risk, or streak controls"]
    else:
        result["drakoln_plan_assessment"] = "PLAN_COMPLETE"
        result["reasons"] = ["money management, technical method, risk management, and entry/exit plans are recorded"]
    return result

