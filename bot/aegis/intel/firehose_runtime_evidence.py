"""Fail-closed point-in-time evidence for Firehose runtime observations."""
from __future__ import annotations

import math
from typing import Any, Mapping


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _no_evidence(reason: str) -> dict[str, str]:
    return {"status": "NO_EVIDENCE", "reason": reason}


def build_runtime_snapshot(
    *,
    ticket: Mapping[str, Any],
    basket: Mapping[str, Any],
    marks: Mapping[str, Any],
    observed_at: Any,
    costs: Mapping[str, Any],
    momentum: Mapping[str, Any],
    remaining_ev: Mapping[str, Any],
) -> dict[str, Any]:
    """Build an exact, costed observation or return an explicit evidence gap."""
    ticket_id = str(ticket.get("ticket_id", "")).strip()
    basket_id = str(ticket.get("basket_id", "")).strip()
    side = str(ticket.get("side", "")).lower()
    if not ticket_id or not basket_id or basket_id != str(basket.get("basket_id", "")).strip():
        return _no_evidence("ticket_basket_mismatch")
    if side not in {"buy", "sell"}:
        return _no_evidence("invalid_side")
    mark_key = "bid" if side == "buy" else "ask"
    mark = _positive(marks.get(mark_key))
    if mark is None:
        return _no_evidence("missing_liquidation_mark")
    timestamp = _finite(observed_at)
    entry = _positive(ticket.get("entry_price"))
    risk = _positive(ticket.get("initial_risk_usd"))
    if timestamp is None or entry is None or risk is None:
        return _no_evidence("missing_ticket_geometry")
    spread = _finite(costs.get("spread_usd"))
    commission = _finite(costs.get("commission_usd"))
    if spread is None or commission is None or spread < 0 or commission < 0:
        return _no_evidence("missing_cost_evidence")
    returns = {key: _finite(momentum.get(key)) for key in ("return_5s", "return_15s", "return_30s")}
    if any(value is None for value in returns.values()):
        return _no_evidence("missing_momentum_evidence")
    ev_value = _finite(remaining_ev.get("value"))
    ev_observed_at = _finite(remaining_ev.get("observed_at"))
    if ev_value is None or ev_observed_at is None or ev_observed_at > timestamp:
        return _no_evidence("missing_remaining_ev_evidence")
    return {
        "status": "OBSERVED",
        "basket_id": basket_id,
        "ticket_id": ticket_id,
        "hypothesis_id": basket.get("hypothesis_id"),
        "family": basket.get("family"),
        "symbol": basket.get("symbol"),
        "side": side,
        "observed_at": timestamp,
        "entry_price": entry,
        "initial_risk_usd": risk,
        "liquidation_mark": mark,
        "liquidation_mark_side": mark_key.upper(),
        "cost_usd": spread + commission,
        "spread_usd": spread,
        "commission_usd": commission,
        "return_5s": returns["return_5s"],
        "return_15s": returns["return_15s"],
        "return_30s": returns["return_30s"],
        "remaining_ev": ev_value,
        "remaining_ev_observed_at": ev_observed_at,
    }


def evaluate_runtime_policy(snapshot: Mapping[str, Any], artifact: Mapping[str, Any] | None) -> dict[str, str]:
    """Keep new runtime policy behavior inactive until an artifact is trusted."""
    if snapshot.get("status") != "OBSERVED":
        return {"action": "NO_EVIDENCE", "reason": "invalid_runtime_snapshot"}
    if not isinstance(artifact, Mapping) or not all(
        artifact.get(field) is True for field in ("validated", "complete", "trusted", "governed")
    ):
        return {"action": "NO_EVIDENCE", "reason": "missing_validated_policy_artifact"}
    return {"action": "NOT_IMPLEMENTED", "reason": "activation_requires_governed_runtime_contract"}
