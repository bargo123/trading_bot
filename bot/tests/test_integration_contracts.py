from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from aegis.intel.integration_contracts import (
    CONTRACT_TYPES,
    CONTRACT_CLASSES,
    CloseIntent,
    ConfirmedClose,
    ConfirmedOutcome,
    EventLedger,
    ExecutionReport,
    FillEvent,
    MarketEvent,
    LifecycleStateMachine,
    OrderedEventBus,
    ORDER_STATES,
    OrderIntent,
    PreflightResult,
    ReconciliationEvent,
    BASKET_STATES,
    make_contract_event,
)


def test_transport_contract_import_does_not_eagerly_load_decision_engine():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import aegis.intel.integration_contracts; print('pandas' in sys.modules)",
        ],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def _market(
    event_id: str,
    timestamp: float,
    *,
    correlation_id: str = "corr-1",
    symbol: str = "EURUSD",
    session: str = "london",
    bid: float | None = 1.1000,
    ask: float | None = 1.1002,
) -> MarketEvent:
    payload = {"session": session}
    if bid is not None:
        payload["bid"] = bid
    if ask is not None:
        payload["ask"] = ask
    return MarketEvent(
        event_id=event_id,
        correlation_id=correlation_id,
        symbol=symbol,
        event_ts=timestamp,
        source="test.feed",
        status="OBSERVED",
        payload=payload,
    )


def test_all_prompt_contracts_are_versioned_and_carry_common_identity():
    assert len(CONTRACT_TYPES) == 21
    assert set(CONTRACT_TYPES) == set(CONTRACT_CLASSES)
    for name, contract_cls in CONTRACT_CLASSES.items():
        contract = contract_cls(
            event_id=f"event-{name}",
            correlation_id="corr-1",
            strategy_id="strategy-1",
            experiment_id="experiment-1",
            basket_id="basket-1",
            symbol="EURUSD",
            event_ts=100.0,
            source="test",
            reason="fixture",
            status="READY",
            payload={"session": "london"},
        )
        row = contract.to_dict()
        assert row["contract_type"] == name
        assert row["schema_version"].endswith(".v1")
        assert row["event_id"] == f"event-{name}"
        assert row["correlation_id"] == "corr-1"
        assert row["strategy_id"] == "strategy-1"
        assert row["experiment_id"] == "experiment-1"
        assert row["basket_id"] == "basket-1"
        assert row["symbol"] == "EURUSD"
        assert row["source"] == "test"
        assert row["status"] == "READY"


def test_event_ledger_accepts_rapid_events_without_reordering_or_dropping():
    ledger = EventLedger(max_quote_age_s=5.0)
    results = [
        ledger.append(_market(f"e-{index}", timestamp), now_ts=100.30)
        for index, timestamp in enumerate((100.00, 100.10, 100.25), 1)
    ]

    assert [result.accepted for result in results] == [True, True, True]
    assert [result.sequence for result in results] == [1, 2, 3]
    assert [event.event_id for event in ledger.replay()] == ["e-1", "e-2", "e-3"]
    assert ledger.stats()["accepted"] == 3
    assert ledger.stats()["quarantined"] == 0


@pytest.mark.parametrize(
    ("event", "now_ts", "reason"),
    [
        (_market("future", 101.0), 100.0, "future_event"),
        (_market("stale", 90.0), 100.0, "stale_quote"),
        (_market("missing-bid", 100.0, bid=None), 100.0, "missing_bid_ask"),
        (_market("missing-ask", 100.0, ask=None), 100.0, "missing_bid_ask"),
        (_market("crossed", 100.0, bid=1.1003, ask=1.1002), 100.0, "crossed_market"),
    ],
)
def test_event_ledger_quarantines_invalid_market_events(event, now_ts, reason):
    ledger = EventLedger(max_quote_age_s=5.0)

    result = ledger.append(event, now_ts=now_ts)

    assert result.accepted is False
    assert result.reason_code == reason
    assert ledger.replay() == ()
    assert ledger.quarantine()[-1]["reason_code"] == reason


def test_event_ledger_rejects_invalid_timestamp_duplicate_and_out_of_order():
    ledger = EventLedger(max_quote_age_s=5.0)
    invalid = ledger.append(
        {
            "contract_type": "MarketEvent",
            "event_id": "bad-time",
            "correlation_id": "corr-1",
            "symbol": "EURUSD",
            "event_ts": "not-a-time",
            "source": "test.feed",
            "status": "OBSERVED",
            "bid": 1.1,
            "ask": 1.1002,
        },
        now_ts=100.0,
    )
    accepted = ledger.append(_market("e-1", 100.0), now_ts=100.0)
    duplicate = ledger.append(_market("e-1", 100.1), now_ts=100.1)
    out_of_order = ledger.append(_market("e-0", 99.9), now_ts=100.1)

    assert invalid.reason_code == "invalid_timestamp"
    assert accepted.accepted is True
    assert duplicate.reason_code == "duplicate_event"
    assert out_of_order.reason_code == "out_of_order"


def test_event_ledger_rejects_quote_after_decision_and_symbol_session_mismatch():
    ledger = EventLedger(max_quote_age_s=5.0)
    decision_late_quote = _market("late-quote", 100.2)
    decision_late_quote.payload["decision_ts"] = 100.1
    after_decision = ledger.append(decision_late_quote, now_ts=100.2)

    first = ledger.append(_market("e-1", 100.0), now_ts=100.0)
    mismatch = ledger.append(
        _market(
            "e-2",
            100.1,
            symbol="GBPUSD",
            session="new-york",
        ),
        now_ts=100.1,
    )

    assert after_decision.reason_code == "quote_after_decision"
    assert first.accepted is True
    assert mismatch.reason_code == "symbol_session_mismatch"


def test_event_ledger_replay_is_deterministic_and_quarantine_is_audit_only():
    ledger = EventLedger(max_quote_age_s=5.0)
    ledger.append(_market("e-1", 100.0), now_ts=100.0)
    ledger.append(_market("future", 102.0), now_ts=100.0)

    first = [event.to_dict() for event in ledger.replay()]
    second = [event.to_dict() for event in ledger.replay()]

    assert first == second
    assert [row["event_id"] for row in first] == ["e-1"]
    assert ledger.quarantine()[0]["event_id"] == "future"


def test_lifecycle_contract_event_is_versioned_and_keeps_broker_payload_audit_only():
    event = make_contract_event(
        OrderIntent,
        event_id="intent-1",
        correlation_id="scan-1",
        symbol="EURUSD",
        event_ts=100.0,
        source="run_broker_paper",
        status="READY",
        reason="fresh_revalidation_pass",
        payload={
            "side": "buy",
            "quantity": 0.01,
            "bid": 1.1,
            "ask": 1.1002,
            "watcher_execution_authority": False,
        },
    )

    assert event["event"] == "firehose_contract.v1"
    assert event["contract_type"] == "OrderIntent"
    assert event["contract"]["schema_version"] == "aegis.order_intent.v1"
    assert event["contract"]["event_id"] == "intent-1"
    assert event["contract"]["payload"]["watcher_execution_authority"] is False


def test_all_runner_lifecycle_contract_types_can_be_emitted():
    classes = (
        PreflightResult,
        ExecutionReport,
        FillEvent,
        CloseIntent,
        ConfirmedClose,
        ConfirmedOutcome,
        ReconciliationEvent,
    )

    events = [
        make_contract_event(
            contract_cls,
            event_id=f"event-{contract_cls.contract_type}",
            correlation_id="ticket-1",
            symbol="EURUSD",
            event_ts=100.0,
            source="run_broker_paper",
            status="OBSERVED",
            payload={"ticket": "ticket-1"},
        )
        for contract_cls in classes
    ]

    assert [event["contract_type"] for event in events] == [
        "PreflightResult",
        "ExecutionReport",
        "FillEvent",
        "CloseIntent",
        "ConfirmedClose",
        "ConfirmedOutcome",
        "ReconciliationEvent",
    ]
    assert all(event["contract"]["schema_version"].endswith(".v1") for event in events)


def test_order_lifecycle_requires_acknowledgement_before_fill_and_close():
    lifecycle = LifecycleStateMachine("order")

    assert lifecycle.state == "INTENDED"
    assert lifecycle.transition("FILLED").accepted is False
    assert lifecycle.state == "INTENDED"
    assert lifecycle.transition("READY").accepted is True
    assert lifecycle.transition("SENT").accepted is True
    assert lifecycle.transition("ACKNOWLEDGED").accepted is True
    assert lifecycle.transition("FILLED").accepted is True
    assert lifecycle.transition("CLOSE_REQUESTED").accepted is True
    assert lifecycle.transition("CLOSED").accepted is True
    assert lifecycle.transition("READY").accepted is False
    assert set(lifecycle.states) == set(ORDER_STATES)


def test_order_lifecycle_requires_a_close_request_before_confirmed_close():
    lifecycle = LifecycleStateMachine("order")
    for state in ("READY", "SENT", "ACKNOWLEDGED", "FILLED"):
        assert lifecycle.transition(state).accepted is True

    assert lifecycle.transition("CLOSED").accepted is False
    assert lifecycle.state == "FILLED"


def test_order_lifecycle_never_promotes_sent_directly_to_a_fill():
    lifecycle = LifecycleStateMachine("order")
    assert lifecycle.transition("READY").accepted is True
    assert lifecycle.transition("SENT").accepted is True

    assert lifecycle.transition("PARTIALLY_FILLED").accepted is False
    assert lifecycle.transition("FILLED").accepted is False
    assert lifecycle.state == "SENT"

    assert lifecycle.transition("ACKNOWLEDGED").accepted is True
    assert lifecycle.transition("PARTIALLY_FILLED").accepted is True


def test_basket_lifecycle_rejects_reopening_after_confirmed_close():
    lifecycle = LifecycleStateMachine("basket", initial="CREATED")

    for state in ("OPENING", "OPEN", "CLOSING", "RECONCILING", "CLOSED"):
        assert lifecycle.transition(state).accepted is True
    result = lifecycle.transition("OPEN")

    assert result.accepted is False
    assert lifecycle.state == "CLOSED"
    assert set(lifecycle.states) == set(BASKET_STATES)


def test_ordered_event_bus_delivers_only_causally_accepted_events():
    bus = OrderedEventBus(max_quote_age_s=5.0)
    delivered = []
    bus.subscribe(lambda event, result: delivered.append((event.event_id, result.sequence)))

    accepted = bus.publish(_market("bus-1", 100.0), now_ts=100.1)
    duplicate = bus.publish(_market("bus-1", 100.1), now_ts=100.1)

    assert accepted.accepted is True
    assert duplicate.reason_code == "duplicate_event"
    assert delivered == [("bus-1", 1)]
    assert [event.event_id for event in bus.replay()] == ["bus-1"]
