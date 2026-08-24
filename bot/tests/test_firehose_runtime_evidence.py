from __future__ import annotations

from aegis.intel.firehose_runtime_evidence import (
    build_runtime_snapshot,
    evaluate_runtime_policy,
)


def _ticket(side: str = "buy") -> dict[str, object]:
    return {
        "ticket_id": "1001",
        "basket_id": "basket-1",
        "side": side,
        "entry_price": 1.1000,
        "initial_risk_usd": 0.15,
    }


def _basket() -> dict[str, object]:
    return {
        "basket_id": "basket-1",
        "hypothesis_id": "hyp-1",
        "family": "breakout",
        "symbol": "EURUSD",
    }


def _costs() -> dict[str, float]:
    return {"spread_usd": 0.01, "commission_usd": 0.02}


def _momentum() -> dict[str, float]:
    return {"return_5s": 0.0001, "return_15s": 0.0002, "return_30s": 0.0003}


def test_buy_snapshot_uses_bid_mark_and_preserves_exact_identity():
    snapshot = build_runtime_snapshot(
        ticket=_ticket("buy"),
        basket=_basket(),
        marks={"bid": 1.1002, "ask": 1.1003},
        observed_at=100.0,
        costs=_costs(),
        momentum=_momentum(),
        remaining_ev={"value": 0.04, "observed_at": 100.0},
    )

    assert snapshot["status"] == "OBSERVED"
    assert snapshot["liquidation_mark"] == 1.1002
    assert snapshot["liquidation_mark_side"] == "BID"
    assert snapshot["basket_id"] == "basket-1"
    assert snapshot["ticket_id"] == "1001"
    assert snapshot["cost_usd"] == 0.03


def test_sell_snapshot_uses_ask_mark():
    snapshot = build_runtime_snapshot(
        ticket=_ticket("sell"),
        basket=_basket(),
        marks={"bid": 1.0997, "ask": 1.0998},
        observed_at=100.0,
        costs=_costs(),
        momentum=_momentum(),
        remaining_ev={"value": 0.04, "observed_at": 100.0},
    )

    assert snapshot["status"] == "OBSERVED"
    assert snapshot["liquidation_mark"] == 1.0998
    assert snapshot["liquidation_mark_side"] == "ASK"


def test_missing_cost_evidence_returns_no_evidence_without_defaulting():
    result = build_runtime_snapshot(
        ticket=_ticket(),
        basket=_basket(),
        marks={"bid": 1.1002, "ask": 1.1003},
        observed_at=100.0,
        costs={"spread_usd": 0.01},
        momentum=_momentum(),
        remaining_ev={"value": 0.04, "observed_at": 100.0},
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_cost_evidence"}


def test_mismatched_ticket_and_basket_returns_no_evidence():
    basket = _basket()
    basket["basket_id"] = "different-basket"

    result = build_runtime_snapshot(
        ticket=_ticket(),
        basket=basket,
        marks={"bid": 1.1002, "ask": 1.1003},
        observed_at=100.0,
        costs=_costs(),
        momentum=_momentum(),
        remaining_ev={"value": 0.04, "observed_at": 100.0},
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "ticket_basket_mismatch"}


def test_policy_evaluation_is_inactive_without_validated_artifact():
    decision = evaluate_runtime_policy({"status": "OBSERVED"}, artifact=None)

    assert decision == {
        "action": "NO_EVIDENCE",
        "reason": "missing_validated_policy_artifact",
    }


def test_policy_evaluation_rejects_untrusted_artifact():
    decision = evaluate_runtime_policy(
        {"status": "OBSERVED"},
        artifact={"validated": True, "complete": True},
    )

    assert decision == {
        "action": "NO_EVIDENCE",
        "reason": "missing_validated_policy_artifact",
    }
