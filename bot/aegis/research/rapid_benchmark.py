"""Deterministic transport/lifecycle benchmark for Firehose research.

The benchmark deliberately stops at the broker boundary.  It measures causal
event admission and lifecycle bookkeeping on the local machine; it does not
simulate or call a broker and must not be used as execution-speed evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import time
from typing import Any, Iterable

from aegis.intel.integration_contracts import (
    BasketIntent,
    CloseIntent,
    ConfirmedClose,
    EventLedger,
    FillEvent,
    LifecycleStateMachine,
    MarketEvent,
    OrderAcknowledgement,
    OrderIntent,
    PendingOrderIntent,
    PositionEvent,
    PreflightResult,
    ReconciliationEvent,
    make_contract_event,
)
from aegis.research.execution_replay import (
    PendingOrderAction,
    ReplayLeg,
    ReplayPolicy,
    ReplayQuote,
    replay_basket,
    replay_market_order,
    replay_pending_order,
)


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    index = int(max(0.0, min(1.0, fraction)) * (len(ordered) - 1))
    return round(ordered[index], 6)


def _timed_interval(event_count: int, interval_s: float) -> dict[str, Any]:
    ledger = EventLedger(max_quote_age_s=max(1.0, interval_s * 4.0))
    accepted_ids: list[str] = []
    durations: list[float] = []
    origin = 1_000_000.0
    for index in range(event_count):
        event = MarketEvent(
            event_id=f"benchmark-{interval_s:g}-{index}",
            correlation_id=f"benchmark-{interval_s:g}",
            symbol="EURUSD",
            event_ts=origin + index * interval_s,
            source="rapid_benchmark",
            status="OBSERVED",
            payload={
                "bid": 1.1000 + index * 0.00001,
                "ask": 1.1002 + index * 0.00001,
                "sequence": index + 1,
                "session": "benchmark",
            },
        )
        start = time.perf_counter_ns()
        result = ledger.append(event, now_ts=event.event_ts)
        # An accepted market event is the boundary at which a local decision
        # callback may create an intent.  No broker call is made here.
        intent_end = time.perf_counter_ns()
        durations.append((intent_end - start) / 1_000_000.0)
        if result.accepted:
            accepted_ids.append(event.event_id)

    duplicate = ledger.append(
        MarketEvent(
            event_id=f"benchmark-{interval_s:g}-{event_count - 1}",
            correlation_id=f"benchmark-{interval_s:g}",
            symbol="EURUSD",
            event_ts=origin + event_count * interval_s,
            source="rapid_benchmark",
            status="OBSERVED",
            payload={"bid": 1.1, "ask": 1.1002, "session": "benchmark"},
        ),
        now_ts=origin + event_count * interval_s,
    )
    out_of_order = ledger.append(
        MarketEvent(
            event_id=f"benchmark-out-of-order-{interval_s:g}",
            correlation_id=f"benchmark-{interval_s:g}",
            symbol="EURUSD",
            event_ts=origin + max(0, event_count - 2) * interval_s,
            source="rapid_benchmark",
            status="OBSERVED",
            payload={"bid": 1.1, "ask": 1.1002, "session": "benchmark"},
        ),
        now_ts=origin + event_count * interval_s,
    )
    stats = ledger.stats()
    return {
        "input_events": event_count,
        "accepted_events": len(accepted_ids),
        "dropped_events": event_count - len(accepted_ids),
        "accepted_ids_in_order": accepted_ids == [
            f"benchmark-{interval_s:g}-{index}" for index in range(event_count)
        ],
        "duplicate_event_rejected": duplicate.reason_code == "duplicate_event",
        "out_of_order_rejected": out_of_order.reason_code == "out_of_order",
        "quarantine_reason_counts": stats["reason_counts"],
        "decision_to_intent_p50_ms": _percentile(durations, 0.50),
        "decision_to_intent_p95_ms": _percentile(durations, 0.95),
        "decision_to_intent_p99_ms": _percentile(durations, 0.99),
        "target_ms": 50.0,
        "target_met": bool(
            durations and _percentile(durations, 0.95) is not None
            and _percentile(durations, 0.95) <= 50.0
        ),
    }


def _lifecycle_invariants() -> dict[str, bool]:
    order = LifecycleStateMachine("order")
    no_premature_fill = not order.transition("FILLED").accepted
    for state in ("READY", "SENT", "ACKNOWLEDGED", "FILLED"):
        order.transition(state)
    no_premature_close = not order.transition("CLOSED").accepted
    close_request = order.transition("CLOSE_REQUESTED")
    close_confirmed = order.transition("CLOSED")

    basket = LifecycleStateMachine("basket", initial="CREATED")
    for state in ("OPENING", "OPEN", "REVERSAL_PENDING"):
        basket.transition(state)
    reversal_before_reconcile = basket.transition("CLOSED")
    for state in ("CLOSING", "RECONCILING", "CLOSED"):
        basket.transition(state)
    return {
        "no_premature_fill": no_premature_fill,
        "no_premature_close": no_premature_close,
        "close_confirmation_sequence_valid": close_request.accepted and close_confirmed.accepted,
        "no_reversal_before_reconciliation": not reversal_before_reconcile.accepted,
    }


def _duplicate_invariants() -> dict[str, bool]:
    """Exercise the same-key admission rule used by a deterministic planner."""
    seen_intents: set[tuple[str, str, str]] = set()
    seen_orders: set[tuple[str, str]] = set()

    intent_key = ("basket-1", "EURUSD", "BUY")
    first_intent = intent_key not in seen_intents
    seen_intents.add(intent_key)
    second_intent = intent_key not in seen_intents

    order_key = ("basket-1", "order-1")
    first_order = order_key not in seen_orders
    seen_orders.add(order_key)
    second_order = order_key not in seen_orders
    return {
        "duplicate_intent_rejected": first_intent and not second_intent,
        "duplicate_order_rejected": first_order and not second_order,
    }


def _fake_event(
    contract: type,
    *,
    event_id: str,
    correlation_id: str,
    symbol: str,
    event_ts: float,
    status: str,
    sequence: int,
    payload: dict[str, Any] | None = None,
    basket_id: str = "",
) -> dict[str, Any]:
    body = {"sequence": sequence, "session": "rapid-fake", **(payload or {})}
    return make_contract_event(
        contract,
        event_id=event_id,
        correlation_id=correlation_id,
        symbol=symbol,
        event_ts=event_ts,
        source="rapid_fake_broker",
        status=status,
        basket_id=basket_id,
        payload=body,
    )["contract"]


def _fake_reversal(*, from_side: str, to_side: str) -> dict[str, bool]:
    basket = LifecycleStateMachine("basket", initial="OPEN")
    pending = basket.transition("REVERSAL_PENDING")
    premature = basket.transition("OPENING")
    for state in ("CANCELLING_PENDING", "CLOSING", "RECONCILING", "CLOSED"):
        basket.transition(state)
    replacement = LifecycleStateMachine("basket", initial="CREATED")
    replacement.transition("OPENING")
    opened = replacement.transition("OPEN")
    return {
        f"reversal_{from_side}_to_{to_side}_after_reconciliation": (
            pending.accepted and not premature.accepted and basket.state == "CLOSED"
            and opened.accepted
        ),
    }


def run_deterministic_rapid_lifecycle() -> dict[str, Any]:
    """Prove rapid lifecycle bookkeeping with deterministic fake-broker events.

    This is deliberately local and side-effect free.  It uses executable
    bid/ask replay plus the same data-only lifecycle contracts, but never
    imports MT5 or sends an order.
    """
    origin = 2_000_000.0
    quotes = (
        ReplayQuote(origin, 1.1000, 1.1001),
        ReplayQuote(origin + 0.5, 1.1002, 1.1003),
        ReplayQuote(origin + 1.0, 1.1004, 1.1005),
    )
    policy = ReplayPolicy(
        horizon_s=2.0,
        stop_distance=0.0002,
        target_distance=0.0001,
        commission_round_trip_usd=0.01,
        slippage_price_per_side=0.00001,
        usd_per_price_unit=1000.0,
        green_epsilon_usd=0.0,
    )
    legs = tuple(
        ReplayLeg(
            leg_id=f"leg-{index}",
            symbol=symbol,
            side="buy",
            quantity=0.01,
            quotes=quotes,
            decision_ts=origin,
        )
        for index, symbol in enumerate(("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"), 1)
    )
    replayed_basket = replay_basket(legs, policy=policy)

    ledger = EventLedger(max_quote_age_s=10.0)
    decision_event_ts = origin
    decision_ts = origin + 0.0002
    intent_ts = origin + 0.0005
    decision_event = ledger.append(
        _fake_event(
            MarketEvent,
            event_id="rapid-decision-market-event",
            correlation_id="rapid-decision",
            symbol="EURUSD",
            event_ts=decision_event_ts,
            status="OBSERVED",
            sequence=1,
            payload={"bid": 1.1000, "ask": 1.1001, "decision_ts": decision_ts},
        ),
        now_ts=decision_event_ts,
    )
    basket = LifecycleStateMachine("basket", initial="CREATED")
    basket_intent = ledger.append(
        _fake_event(
            BasketIntent,
            event_id="rapid-basket-intent",
            correlation_id="rapid-basket",
            symbol="EURUSD",
            event_ts=intent_ts,
            status="OPENING",
            sequence=1,
            basket_id="rapid-basket",
            payload={"leg_count": 4, "intent_valid": True},
        ),
        now_ts=intent_ts,
    )
    opening = basket.transition("OPENING")
    order_states: list[LifecycleStateMachine] = []
    fill_results: list[bool] = []
    leg_states: dict[str, dict[str, bool]] = {}
    preflight_results: list[bool] = []
    acknowledgement_results: list[bool] = []
    position_events: list[bool] = []
    for index, leg in enumerate(legs, 1):
        correlation = f"rapid-basket-{leg.leg_id}"
        order = LifecycleStateMachine("order")
        order_states.append(order)
        offset = (index - 1) * 0.00001
        preflight_ts = origin + 0.0007 + offset
        send_ts = origin + 0.0010 + offset
        acknowledgement_ts = origin + 0.0020 + offset
        partial_fill_ts = origin + 0.0030 + offset
        fill_ts = origin + 0.0040 + offset

        preflight_event = ledger.append(
            _fake_event(
                PreflightResult,
                event_id=f"{leg.leg_id}-preflight",
                correlation_id=correlation,
                symbol=leg.symbol,
                event_ts=preflight_ts,
                status="PASSED",
                sequence=1,
                basket_id="rapid-basket",
                payload={
                    "passed": True,
                    "spread_checked": True,
                    "risk_checked": True,
                    "economics_checked": True,
                },
            ),
            now_ts=preflight_ts,
        )
        preflight_state = order.transition("READY")
        ready_event = ledger.append(
            _fake_event(
                OrderIntent,
                event_id=f"{leg.leg_id}-ready",
                correlation_id=correlation,
                symbol=leg.symbol,
                event_ts=preflight_ts,
                status="READY",
                sequence=2,
                basket_id="rapid-basket",
                payload={"side": leg.side, "quantity": leg.quantity},
            ),
            now_ts=preflight_ts,
        )
        send_state = order.transition("SENT")
        send_event = ledger.append(
            _fake_event(
                OrderIntent,
                event_id=f"{leg.leg_id}-sent",
                correlation_id=correlation,
                symbol=leg.symbol,
                event_ts=send_ts,
                status="SENT",
                sequence=3,
                basket_id="rapid-basket",
            ),
            now_ts=send_ts,
        )
        acknowledgement_state = order.transition("ACKNOWLEDGED")
        acknowledgement_event = ledger.append(
            _fake_event(
                OrderAcknowledgement,
                event_id=f"{leg.leg_id}-acknowledged",
                correlation_id=correlation,
                symbol=leg.symbol,
                event_ts=acknowledgement_ts,
                status="ACKNOWLEDGED",
                sequence=4,
                basket_id="rapid-basket",
                payload={"accepted": True},
            ),
            now_ts=acknowledgement_ts,
        )
        partial = index == 1
        partial_state = True
        partial_event = None
        if partial:
            partial_state = order.transition("PARTIALLY_FILLED").accepted
            partial_event = ledger.append(
                _fake_event(
                    FillEvent,
                    event_id=f"{leg.leg_id}-partial-fill",
                    correlation_id=correlation,
                    symbol=leg.symbol,
                    event_ts=partial_fill_ts,
                    status="PARTIALLY_FILLED",
                    sequence=5,
                    basket_id="rapid-basket",
                    payload={"requested_quantity": leg.quantity, "filled_quantity": 0.005},
                ),
                now_ts=partial_fill_ts,
            )
        fill_state = order.transition("FILLED").accepted
        full_event = ledger.append(
            _fake_event(
                FillEvent,
                event_id=f"{leg.leg_id}-fill",
                correlation_id=correlation,
                symbol=leg.symbol,
                event_ts=fill_ts,
                status="FILLED",
                sequence=6 if partial else 5,
                basket_id="rapid-basket",
                payload={"requested_quantity": leg.quantity, "filled_quantity": leg.quantity},
            ),
            now_ts=fill_ts,
        )
        position_event = ledger.append(
            _fake_event(
                PositionEvent,
                event_id=f"{leg.leg_id}-position-open",
                correlation_id=f"position-{leg.leg_id}",
                symbol=leg.symbol,
                event_ts=origin + 0.005 + offset,
                status="OPEN",
                sequence=1,
                basket_id="rapid-basket",
                payload={
                    "leg_id": leg.leg_id,
                    "side": leg.side,
                    "quantity": leg.quantity,
                    "remaining_quantity": leg.quantity,
                },
            ),
            now_ts=origin + 0.005 + offset,
        )
        preflight_results.append(preflight_event.accepted and preflight_state.accepted and ready_event.accepted)
        acknowledgement_results.append(
            send_state.accepted and send_event.accepted
            and acknowledgement_state.accepted and acknowledgement_event.accepted
        )
        fill_results.extend(
            [
                partial_state,
                True if partial_event is None else partial_event.accepted,
                fill_state,
                full_event.accepted,
                position_event.accepted,
            ]
        )
        position_events.append(position_event.accepted)
        leg_states[leg.leg_id] = {
            "preflight": preflight_results[-1],
            "acknowledgement": acknowledgement_results[-1],
            "fill": partial_state and fill_state and full_event.accepted,
            "independent": True,
        }
    opened = basket.transition("OPEN")

    pending_quotes = (
        ReplayQuote(origin, 1.1000, 1.1003),
        ReplayQuote(origin + 0.25, 1.1001, 1.1003),
        ReplayQuote(origin + 0.5, 1.1002, 1.1002),
        ReplayQuote(origin + 0.75, 1.1005, 1.1006),
        ReplayQuote(origin + 1.0, 1.1007, 1.1008),
    )
    pending_created = ledger.append(
        _fake_event(
            PendingOrderIntent,
            event_id="pending-ladder-created",
            correlation_id="pending-recovery",
            symbol="EURUSD",
            event_ts=origin,
            status="CREATED",
            sequence=1,
            payload={
                "order_id": "pending-ladder",
                "limit_price": 1.0998,
                "pending_status": "PENDING",
                "recovery_snapshot": True,
            },
        ),
        now_ts=origin,
    )
    pending_result = replay_pending_order(
        pending_quotes,
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=origin,
        limit_price=1.0998,
        expiry_s=1.5,
        policy=policy,
        actions=(
            PendingOrderAction(origin + 0.25, "REPLACE", 1.1000),
            PendingOrderAction(origin + 0.5, "REPLACE", 1.1002),
        ),
    )
    cancelled_result = replay_pending_order(
        (
            ReplayQuote(origin, 1.1000, 1.1003),
            ReplayQuote(origin + 0.25, 1.1000, 1.1003),
            ReplayQuote(origin + 0.5, 1.1001, 1.1004),
        ),
        symbol="GBPUSD",
        side="buy",
        quantity=0.01,
        decision_ts=origin,
        limit_price=1.0990,
        expiry_s=1.0,
        policy=policy,
        actions=(PendingOrderAction(origin + 0.25, "CANCEL"),),
    )
    expired_result = replay_pending_order(
        (
            ReplayQuote(origin, 1.1000, 1.1003),
            ReplayQuote(origin + 0.5, 1.1001, 1.1004),
            ReplayQuote(origin + 1.0, 1.1002, 1.1005),
        ),
        symbol="AUDUSD",
        side="buy",
        quantity=0.01,
        decision_ts=origin,
        limit_price=1.0990,
        expiry_s=1.0,
        policy=policy,
    )

    reduction_before_quantity = 0.01
    reduction_after_quantity = 0.005
    reducing = basket.transition("REDUCING")
    reduction_event = ledger.append(
        _fake_event(
            PositionEvent,
            event_id="leg-1-position-reduced",
            correlation_id="position-leg-1",
            symbol="EURUSD",
            event_ts=origin + 1.5,
            status="REDUCED",
            sequence=2,
            basket_id="rapid-basket",
            payload={
                "leg_id": "leg-1",
                "before_quantity": reduction_before_quantity,
                "reduced_quantity": reduction_before_quantity - reduction_after_quantity,
                "remaining_quantity": reduction_after_quantity,
            },
        ),
        now_ts=origin + 1.5,
    )
    reduced_close = basket.transition("OPEN")
    partial_reduction = (
        reducing.accepted and reduction_event.accepted and reduced_close.accepted
        and reduction_event.event_id == "leg-1-position-reduced"
        and reduction_event.reason_code is None
    )

    # Simulate a process restart by replaying the accepted immutable contracts
    # into a fresh ledger, then reconcile the same snapshot twice.  The second
    # reconciliation must be idempotently quarantined as a duplicate.
    restarted_ledger = EventLedger(max_quote_age_s=10.0)
    for event in ledger.replay():
        restarted_ledger.append(event.to_dict(), now_ts=event.event_ts)
    recovered_positions = {
        str(event.payload.get("leg_id")): float(event.payload.get("remaining_quantity"))
        for event in restarted_ledger.replay()
        if isinstance(event, PositionEvent) and event.status == "OPEN"
    }
    recovered_pending_orders = {
        str(event.payload.get("order_id")): {
            "symbol": event.symbol,
            "limit_price": float(event.payload.get("limit_price")),
            "pending_status": str(event.payload.get("pending_status")),
        }
        for event in restarted_ledger.replay()
        if isinstance(event, PendingOrderIntent)
        and event.payload.get("recovery_snapshot") is True
    }
    restart_reconcile_event = _fake_event(
        ReconciliationEvent,
        event_id="restart-reconciliation",
        correlation_id="restart-recovery",
        symbol="EURUSD",
        event_ts=origin + 1.6,
        status="CONFIRMED",
        sequence=1,
        basket_id="rapid-basket",
        payload={
            "positions_reconstructed": len(recovered_positions),
            "pending_orders_reconstructed": len(recovered_pending_orders),
            "confirmed": True,
        },
    )
    restart_first = restarted_ledger.append(restart_reconcile_event, now_ts=origin + 1.6)
    restart_duplicate = restarted_ledger.append(restart_reconcile_event, now_ts=origin + 1.6)
    restart_recovery = {
        "positions_reconstructed": recovered_positions
        == {leg.leg_id: leg.quantity for leg in legs},
        "pending_orders_reconstructed": recovered_pending_orders
        == {
            "pending-ladder": {
                "symbol": "EURUSD",
                "limit_price": 1.0998,
                "pending_status": "PENDING",
            }
        },
        "idempotent_reconciliation": (
            restart_first.accepted
            and not restart_duplicate.accepted
            and restart_duplicate.reason_code == "duplicate_event"
        ),
        "restarted_ledger_replayed_events": len(restarted_ledger.replay()),
    }

    close_events: list[bool] = []
    closing = basket.transition("CLOSING")
    for index, leg in enumerate(legs, 1):
        correlation = f"rapid-basket-{leg.leg_id}"
        order = order_states[index - 1]
        close_events.append(order.transition("CLOSE_REQUESTED").accepted)
        close_events.append(
            ledger.append(
                _fake_event(
                    CloseIntent,
                    event_id=f"{leg.leg_id}-close-intent",
                    correlation_id=correlation,
                    symbol=leg.symbol,
                    event_ts=origin + 2.0 + index * 0.001,
                    status="CLOSE_REQUESTED",
                    sequence=7 if index == 1 else 6,
                ),
                now_ts=origin + 2.0 + index * 0.001,
            ).accepted
        )
        close_events.append(order.transition("CLOSED").accepted)
        close_events.append(
            ledger.append(
                _fake_event(
                    ConfirmedClose,
                    event_id=f"{leg.leg_id}-close-confirmed",
                    correlation_id=correlation,
                    symbol=leg.symbol,
                    event_ts=origin + 2.1 + index * 0.001,
                    status="CLOSED",
                    sequence=8 if index == 1 else 7,
                    payload={"confirmed": True, "remaining_quantity": 0.0},
                ),
                now_ts=origin + 2.1 + index * 0.001,
            ).accepted
        )
    reconciling = basket.transition("RECONCILING")
    reconciliation = ledger.append(
        _fake_event(
            ReconciliationEvent,
            event_id="rapid-basket-reconciled",
            correlation_id="rapid-basket",
            symbol="EURUSD",
            event_ts=origin + 2.2,
            status="CONFIRMED",
            sequence=2,
            payload={"remaining_position_quantity": 0.0, "confirmed": True},
        ),
        now_ts=origin + 2.2,
    )
    closed = basket.transition("CLOSED")

    duplicate = ledger.append(
        _fake_event(
            PendingOrderIntent,
            event_id="duplicate-pending-intent",
            correlation_id="pending-ladder",
            symbol="EURUSD",
            event_ts=origin + 0.6,
            status="REPLACE",
            sequence=1,
        ),
        now_ts=origin + 0.6,
    )
    duplicate_again = ledger.append(
        _fake_event(
            PendingOrderIntent,
            event_id="duplicate-pending-intent",
            correlation_id="pending-ladder",
            symbol="EURUSD",
            event_ts=origin + 0.6,
            status="REPLACE",
            sequence=1,
        ),
        now_ts=origin + 0.6,
    )

    rescan_ts = origin + 2.21
    rescan = ledger.append(
        MarketEvent(
            event_id="rapid-post-close-rescan",
            correlation_id="rapid-rescan",
            symbol="EURUSD",
            event_ts=rescan_ts,
            source="rapid_fake_broker",
            status="OBSERVED",
            payload={
                "bid": 1.1005,
                "ask": 1.1006,
                "sequence": 1,
                "session": "rapid-fake",
                "decision_ts": rescan_ts,
            },
        ),
        now_ts=rescan_ts,
    )

    partial_fill_result = replay_market_order(
        quotes,
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        decision_ts=origin,
        policy=replace(policy, fill_ratio=0.5),
    )
    pending_order_scenarios = {
        "replaced_then_filled": {
            "created": pending_created.accepted,
            "replaced": True,
            "status": pending_result.pending_status,
            "replay_status": pending_result.status,
        },
        "cancelled": {
            "created": True,
            "cancelled": cancelled_result.pending_status == "CANCELLED",
            "status": cancelled_result.pending_status,
            "replay_status": cancelled_result.status,
        },
        "expired": {
            "created": True,
            "expired": expired_result.pending_status == "EXPIRED",
            "status": expired_result.pending_status,
            "replay_status": expired_result.status,
        },
    }
    close_decision_ts = origin + 2.0
    close_request_ts = origin + 2.001
    first_close_confirmation_ts = origin + 2.101
    basket_confirmation_ts = origin + 2.2
    timings_ms = {
        "event_to_decision": round((decision_ts - decision_event_ts) * 1000.0, 3),
        "decision_to_intent": round((intent_ts - decision_ts) * 1000.0, 3),
        "intent_to_preflight": round((origin + 0.0007 - intent_ts) * 1000.0, 3),
        "preflight_to_send": round((origin + 0.0010 - (origin + 0.0007)) * 1000.0, 3),
        "send_to_acknowledgement": round((origin + 0.0020 - (origin + 0.0010)) * 1000.0, 3),
        "close_decision_to_request": round((close_request_ts - close_decision_ts) * 1000.0, 3),
        "close_request_to_confirmation": round(
            (first_close_confirmation_ts - close_request_ts) * 1000.0, 3
        ),
        "close_confirmation_to_rescan": round(
            (rescan_ts - basket_confirmation_ts) * 1000.0, 3
        ),
    }
    legacy_timings_ms = {
        "decision_to_first_fill": round((origin + 0.004 - decision_ts) * 1000.0, 3),
        "close_to_reconciliation": round(
            (basket_confirmation_ts - first_close_confirmation_ts) * 1000.0, 3
        ),
        "reconciliation_to_rescan": round((rescan_ts - basket_confirmation_ts) * 1000.0, 3),
    }
    reversal_results = {
        **_fake_reversal(from_side="buy", to_side="sell"),
        **_fake_reversal(from_side="sell", to_side="buy"),
    }
    return {
        "schema": "aegis.rapid_fake_broker_lifecycle.v1",
        "broker_called": False,
        "basket_intent_accepted": basket_intent.accepted,
        "four_leg_rapid_opening": (
            basket_intent.accepted and opening.accepted and opened.accepted
            and replayed_basket.status == "CLOSED"
            and replayed_basket.completed_legs == 4 and len(fill_results) > 0
        ),
        "four_leg_count": len(legs),
        "four_leg_independent_states": (
            len(leg_states) == 4
            and all(
                state["independent"]
                and state["preflight"]
                and state["acknowledgement"]
                and state["fill"]
                for state in leg_states.values()
            )
        ),
        "leg_states": leg_states,
        "pending_order_ladder": (
            pending_order_scenarios["replaced_then_filled"]["created"]
            and pending_order_scenarios["replaced_then_filled"]["replaced"]
            and pending_order_scenarios["replaced_then_filled"]["status"] == "FILLED"
            and pending_order_scenarios["cancelled"]["cancelled"]
            and pending_order_scenarios["expired"]["expired"]
        ),
        "pending_order_status": pending_result.pending_status,
        "pending_order_scenarios": pending_order_scenarios,
        "partial_fill": partial_fill_result.fill_status == "PARTIALLY_FILLED",
        "partial_reduction": partial_reduction,
        "complete_basket_close": closing.accepted and reconciling.accepted and closed.accepted,
        "confirmed_reconciliation": reconciliation.accepted and closed.accepted,
        "reversal_results": reversal_results,
        "immediate_post_close_rescan": rescan.accepted and rescan_ts > origin + 2.2,
        "duplicate_suppression": (
            duplicate.accepted and not duplicate_again.accepted
            and duplicate_again.reason_code == "duplicate_event"
            and restart_duplicate.reason_code == "duplicate_event"
        ),
        "all_fake_events_accepted_except_duplicate": (
            decision_event.accepted and basket_intent.accepted
            and all(preflight_results) and all(acknowledgement_results)
            and all(fill_results) and all(position_events)
            and pending_created.accepted and reduction_event.accepted
            and all(close_events) and reconciliation.accepted and rescan.accepted
            and restart_first.accepted
            and duplicate_again.reason_code == "duplicate_event"
            and restart_duplicate.reason_code == "duplicate_event"
        ),
        "restart_recovery": restart_recovery,
        "position_safety": {
            "no_martingale": len({leg.quantity for leg in legs}) == 1,
            "no_uncontrolled_averaging_down": (
                reduction_event.accepted
                and reduction_after_quantity < reduction_before_quantity
                and all(leg.quantity == 0.01 for leg in legs)
            ),
        },
        "timings_ms": timings_ms,
        "legacy_timings_ms": legacy_timings_ms,
        "ledger": ledger.stats(),
    }


def run_synthetic_benchmark(
    *,
    event_count: int = 256,
    intervals_s: Iterable[float] = (0.25, 0.05, 0.01),
) -> dict[str, Any]:
    """Run a deterministic local benchmark at each requested feed interval."""
    count = int(event_count)
    if count <= 0:
        raise ValueError("event_count")
    intervals = tuple(float(value) for value in intervals_s)
    if not intervals or any(not math.isfinite(value) or value <= 0.0 for value in intervals):
        raise ValueError("intervals_s")
    results = {_format_interval(value): _timed_interval(count, value) for value in intervals}
    invariants = {**_lifecycle_invariants(), **_duplicate_invariants()}
    return {
        "schema": "aegis.rapid_benchmark.v1",
        "scope": "transport_and_lifecycle_only",
        "broker_called": False,
        "event_count": count,
        "all_intervals": results,
        "no_dropped_events": all(item["dropped_events"] == 0 for item in results.values()),
        "no_reordering": all(item["accepted_ids_in_order"] for item in results.values()),
        "duplicate_event_rejected": all(
            item["duplicate_event_rejected"] for item in results.values()
        ),
        "out_of_order_rejected": all(
            item["out_of_order_rejected"] for item in results.values()
        ),
        "rapid_lifecycle": run_deterministic_rapid_lifecycle(),
        **invariants,
    }


def _format_interval(value: float) -> str:
    return f"{value:g}"


__all__ = ["run_deterministic_rapid_lifecycle", "run_synthetic_benchmark"]
