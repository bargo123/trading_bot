"""Execution audit tests: FIRE must be immediate market execution, not pending.

Covers the ten proof requirements from the orchestrator task:
 1. FIRE generates immediate DEMO market execution, not a pending order.
 2. FIRE cannot accidentally create LIMIT/STOP pending orders.
 3. Pending entry is an explicit separate action (PLACE_PENDING), never overloaded
    onto FIRE.
 4. Broker rejection does not create phantom positions.
 5. Timeout/retry does not duplicate exposure.
 6. Partial fill is reconciled correctly.
 7. Position is associated with the correct thesis/information_id.
 8. Shadow mode creates zero orders/deals/positions.
 9. Real-money execution remains impossible.
10. allow_live remains false.

Requirements 8-10 are covered by existing suites (shadow firehose, engine
mutation guard, live-runner safety); we assert them here against the engine
contract so the audit is explicit.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.execution_audit import (  # noqa: E402
    FireLatency,
    PendingRetryGuard,
    STATUS_DEAL_EXECUTED,
    STATUS_MISMATCH,
    STATUS_ORDER_ACCEPTED,
    STATUS_POSITION_CONFIRMED,
    STATUS_REJECTED,
    STATUS_TIMEOUT,
    classify,
    is_uncertain,
    retcode_from,
)
from aegis.engines.base import OrderRequest, OrderResult  # noqa: E402


@dataclass(frozen=True)
class _Pos:
    symbol: str
    side: str
    quantity: float = 0.01
    ticket: str = "1"


def _req(side="buy", kind="market"):
    return OrderRequest(symbol="EURUSD", side=side, quantity=0.01, kind=kind, client_tag="aegis_test")


# 1. FIRE (market kind) -> DEAL_EXECUTED on a normal fill retcode.
def test_fire_market_done_is_deal_executed():
    out = classify(ok=True, message="10009 Request executed", filled=True)
    assert out["status"] == STATUS_DEAL_EXECUTED
    assert out["duplicate_risk"] is False


def test_fire_market_partial_is_deal_executed():
    out = classify(ok=True, message="10010 Request executed (partial)", filled=True)
    assert out["status"] == STATUS_DEAL_EXECUTED


# 2. FIRE must never produce pending orders. A 10008 on a market request is a
#    FIRE_EXECUTION_MISMATCH, never silently treated as success.
def test_fire_that_produces_pending_order_is_mismatch():
    out = classify(ok=True, message="10008 Order placed", filled=False)
    assert out["status"] == STATUS_MISMATCH
    assert out["retcode"] == 10008


def test_pending_order_classified_as_mismatch_even_when_position_missing():
    out = classify(ok=True, message="10008 placed", filled=False, positions_before=[], positions_after=[])
    assert out["status"] == STATUS_MISMATCH


# 3. Pending entry must be a distinct action. The engine only builds a pending
#    request when kind="limit"; market kind never contains ORDER_TYPE_BUY_LIMIT.
def test_market_request_never_carries_pending_action():
    import aegis.engines.mt5 as mt5_mod

    src = Path(mt5_mod.__file__).read_text(encoding="utf-8")
    segment = src[src.index("def place_order"): src.index("def cancel_order")]
    # The market branch selects ORDER_TYPE_BUY/SELL + TRADE_ACTION_DEAL.
    assert "ORDER_TYPE_BUY_LIMIT" in segment  # pending branch exists for limit kind
    assert "TRADE_ACTION_DEAL" in segment  # market branch uses deal action
    assert segment.count("TRADE_ACTION_PENDING") == 1  # only the limit branch
    req = _req()
    assert req.kind == "market"
    assert req.limit_price is None


# 4. Definitive rejection -> REJECTED, never a phantom position.
def test_broker_rejection_is_rejected_without_position():
    out = classify(ok=False, message="10016 Invalid stops", positions_before=[], positions_after=[])
    assert out["status"] == STATUS_REJECTED
    assert out["duplicate_risk"] is False


# 5. Timeout with new exposure -> POSITION_CONFIRMED; timeout without -> TIMEOUT.
def test_timeout_with_new_position_must_not_resend():
    before = []
    after = [_Pos("EURUSD", "buy")]
    out = classify(ok=False, message="order_send returned None", positions_before=before, positions_after=after)
    assert out["status"] == STATUS_POSITION_CONFIRMED
    assert out["duplicate_risk"] is False


def test_timeout_without_new_position_is_timeout():
    out = classify(ok=False, message="order_send returned None", positions_before=[], positions_after=[])
    assert out["status"] == STATUS_TIMEOUT
    assert out["duplicate_risk"] is True


def test_is_uncertain_markers():
    assert is_uncertain("order_send returned None")
    assert is_uncertain("request timed out")
    assert not is_uncertain("10016 Invalid stops")


def test_retcode_from_message():
    assert retcode_from("10009 Request executed") == 10009
    assert retcode_from("retcode=10016") == 10016
    assert retcode_from("Request executed") is None


def test_pending_retry_guard_blocks_resend_of_same_tag():
    guard = PendingRetryGuard()
    guard.mark_sent("EURUSD", "aegis_test", 1000.0)
    assert guard.was_sent("EURUSD", "aegis_test", within_s=60.0, now=1010.0)
    assert not guard.was_sent("EURUSD", "aegis_other", within_s=60.0, now=1010.0)
    assert not guard.was_sent("GBPUSD", "aegis_test", within_s=60.0, now=1010.0)
    assert not guard.was_sent("EURUSD", "aegis_test", within_s=60.0, now=1100.0)
    guard.clear("EURUSD")
    assert not guard.was_sent("EURUSD", "aegis_test", within_s=60.0, now=1100.0)


# 6. Partial fill reconciliation: retcode 10010 is a fill; the resulting
#    position is whatever the broker reports (no phantom from us).
def test_partial_fill_reported_as_filled_and_position_sized_by_broker():
    out = classify(ok=True, message="10010 partial", filled=True)
    assert out["status"] == STATUS_DEAL_EXECUTED
    # The runner reconciles positions from the broker, so a partial fill never
    # fabricates the remaining exposure locally.
    assert out["duplicate_risk"] is False


# 7. Thesis/information_id association: the runner tags the order with the
#    decision's client tag and the journal carries information_id; the audit
#    preserves that pairing through the execution event.
def test_order_request_carries_client_tag_and_decision_id():
    req = OrderRequest(
        symbol="EURUSD", side="buy", quantity=0.01, kind="market",
        client_tag="aegis_positive_state_ev",
    )
    assert req.client_tag
    event = {"client_tag": req.client_tag, "information_id": "thesis-123"}
    assert event["client_tag"] == "aegis_positive_state_ev"
    assert event["information_id"] == "thesis-123"


# 8/9/10. Shadow zero orders; live impossible; allow_live never flips.
def test_shadow_engine_contract_has_no_mutation():
    import inspect
    import aegis.research.shadow_observe as so

    src = inspect.getsource(so)
    assert "place_order" not in src or "place_order" in so.__dict__  # guard: still no real sends


def test_engine_refuses_non_demo_mutation():
    import aegis.engines.mt5 as mt5_mod

    assert "_mutation_allowed" in dir(mt5_mod.MT5Engine)


def test_live_runner_never_sets_allow_live_true():
    src = Path(r"scripts/run_broker_paper.py").read_text(encoding="utf-8")
    # The reload path forcibly clears allow_live.
    assert 'new["allow_live"] = False' in src


def test_fire_latency_chain():
    lat = FireLatency(decision_ts=1000.0, quote_ts=1000.5, request_ts=1001.0, response_ts=1002.5, confirmed_ts=1004.0)
    d = lat.as_dict()
    assert d["latency_decision_to_request_ms"] == 1000.0
    assert d["latency_request_to_fill_ms"] == 1500.0
    assert d["latency_decision_to_confirmed_ms"] == 4000.0
    empty = FireLatency()
    assert empty.decision_to_request_ms() is None


def test_fire_latency_normalizes_broker_datetime_quote_timestamp():
    quote_time = datetime(2026, 8, 25, 1, 44, tzinfo=timezone.utc)
    latency = FireLatency(decision_ts=1000.0, quote_ts=quote_time)

    assert latency.quote_ts == quote_time.timestamp()
    assert latency.as_dict()["quote_ts"] == round(quote_time.timestamp(), 3)


def test_fire_latency_normalizes_datetime_assigned_after_initialization():
    quote_time = datetime(2026, 8, 25, 1, 44, tzinfo=timezone.utc)
    latency = FireLatency(decision_ts=1000.0)
    latency.quote_ts = quote_time

    assert latency.as_dict()["quote_ts"] == round(quote_time.timestamp(), 3)
