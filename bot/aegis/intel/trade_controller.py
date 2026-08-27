"""Single canonical owner for per-ticket lifecycle actions."""
from __future__ import annotations

from typing import Any, Mapping


CANONICAL_ACTIONS = frozenset({"HOLD", "LOCK", "HARVEST", "SCRATCH", "ABORT"})


def _canonical_action(source_action: object, reason: object) -> str:
    action = str(source_action or "HOLD").upper()
    why = str(reason or "").lower()
    if action in {"TAKE", "QUICK_TAKE", "HARVEST"}:
        return "HARVEST"
    if action in {"SCRATCH", "REDUCE"}:
        return "SCRATCH"
    if action in {"ABORT"}:
        return "ABORT"
    if action in {"EXIT", "TIME_EXIT"}:
        if any(token in why for token in (
            "remaining_ev", "regime", "invalid", "revoked", "abort", "tail",
        )):
            return "ABORT"
        if any(token in why for token in ("harvest", "take", "target", "giveback", "profit")):
            return "HARVEST"
        return "SCRATCH"
    if action == "LOCK":
        return "LOCK"
    return "HOLD"


class TradeController:
    """Combine evidence adapters into exactly one canonical action.

    ProfitManager and FastExit remain evidence producers.  The runner calls
    this controller once and closes only for HARVEST, SCRATCH, or ABORT.
    """

    def decide(
        self,
        profit_manager_verdict: Mapping[str, Any] | None,
        fast_verdict: Mapping[str, Any] | None,
        *,
        remaining_ev: float | None = None,
        harvest_ev_comparison: Mapping[str, Any] | None = None,
        evidence_snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        pm = dict(profit_manager_verdict or {})
        fast = dict(fast_verdict or {})
        candidates = [
            ("profit_manager", pm, _canonical_action(pm.get("action"), pm.get("reason"))),
            ("fast_exit", fast, _canonical_action(fast.get("action"), fast.get("reason"))),
        ]
        priority = {"HOLD": 0, "LOCK": 1, "HARVEST": 2, "SCRATCH": 3, "ABORT": 4}
        source, selected, action = max(
            candidates,
            key=lambda item: priority[item[2]],
        )
        why_hold = "; ".join(
            str(item.get("why")) for _, item, mapped in candidates
            if mapped in {"HOLD", "LOCK"} and item.get("why")
        )
        why_exit = str(selected.get("why") or selected.get("reason") or "") if action in {
            "HARVEST", "SCRATCH", "ABORT"
        } else ""
        result = {
            "action": action,
            "reason": str(selected.get("reason") or f"controller_{action.lower()}"),
            "policy": selected.get("policy"),
            "source": source,
            "why_hold": why_hold,
            "why_exit": why_exit,
            "why": why_exit or why_hold,
            "remaining_ev": remaining_ev,
            "harvest_ev_comparison": dict(harvest_ev_comparison or {}),
            "evidence_snapshot": dict(evidence_snapshot or {}),
        }
        if action == "HOLD" and not result["why_hold"]:
            result["why_hold"] = "no exit policy triggered"
        return result
