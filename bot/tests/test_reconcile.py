"""Library tests for deal-cursor reconciliation. Does not start the paper runner."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aegis.reconcile import (
    ReconcileCursor,
    aggregate_confirmed_exit_deals,
    reconcile_new_deals,
)


def test_aggregate_confirmed_exit_deals_uses_exact_position_and_broker_costs():
    facts = aggregate_confirmed_exit_deals(
        [
            {
                "ticket": "entry-deal",
                "order": "entry-order",
                "position_id": "P1",
                "symbol": "EURUSD",
                "entry": 0,
                "profit": 0.0,
                "commission": -0.01,
                "swap": 0.0,
                "fee": -0.002,
                "price": 1.1000,
                "qty": 0.01,
                "time": "2026-08-14T10:00:00Z",
            },
            {
                "ticket": "exit-deal-1",
                "order": "exit-order-1",
                "position_id": "P1",
                "symbol": "EURUSD",
                "entry": 1,
                "profit": 0.12,
                "commission": -0.02,
                "swap": -0.01,
                "fee": -0.003,
                "price": 1.1010,
                "qty": 0.006,
                "time": "2026-08-14T10:00:01Z",
            },
            {
                "ticket": "exit-deal-2",
                "order": "exit-order-2",
                "position_id": "P1",
                "symbol": "EURUSD",
                "entry": 1,
                "profit": 0.03,
                "commission": -0.01,
                "swap": 0.0,
                "fee": -0.002,
                "price": 1.1012,
                "qty": 0.004,
                "time": "2026-08-14T10:00:02Z",
            },
            {
                "ticket": "other-exit",
                "order": "other-order",
                "position_id": "P2",
                "symbol": "EURUSD",
                "entry": 1,
                "profit": 99.0,
                "commission": 0.0,
                "swap": 0.0,
                "fee": 0.0,
                "price": 2.0,
                "qty": 1.0,
                "time": "2026-08-14T10:00:03Z",
            },
        ],
        position_id="P1",
    )

    assert facts is not None
    assert facts["position_id"] == "P1"
    assert facts["deal_tickets"] == ["exit-deal-1", "exit-deal-2"]
    assert facts["gross_realized_pnl_usd"] == pytest.approx(0.15)
    assert facts["cost_usd"] == pytest.approx(0.045)
    assert facts["realized_net_usd"] == pytest.approx(0.105)
    assert facts["actual_close_price"] == pytest.approx(1.10108)
    assert facts["confirmed"] is True


def test_aggregate_confirmed_exit_deals_is_fail_closed_without_exact_exit():
    assert aggregate_confirmed_exit_deals(
        [{"position_id": "P1", "entry": 0, "profit": 0.0}],
        position_id="P1",
    ) is None


def test_reconcile_emits_native_tp_once_with_realized_net_pnl():
    deals = [
        {
            "ticket": "10",
            "order": "20",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 0,
            "profit": 0.0,
            "commission": -0.01,
            "swap": 0.0,
            "comment": "aegis_entry",
            "time": "2026-08-14T10:00:00.001Z",
        },
        {
            "ticket": "11",
            "order": "21",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 1,
            "profit": 0.08,
            "commission": -0.02,
            "swap": -0.01,
            "fee": -0.005,
            "comment": "",
            "reason": 5,
            "time": "2026-08-14T10:01:00.123Z",
        },
    ]
    cursor = ReconcileCursor()
    first = reconcile_new_deals(deals, cursor)
    second = reconcile_new_deals(deals, cursor)
    exits = [row for row in first if row.is_exit]
    assert [row.close_reason for row in exits] == ["tp"]
    assert exits[0].pnl == pytest.approx(0.045)
    assert exits[0].position == "30"
    assert second == []


def test_reconcile_preserves_ticket_identity_and_millisecond_order_chronology():
    same_time = "2026-08-14T10:00:00.123Z"
    deals = [
        {
            "ticket": "002",
            "order": "10",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 0,
            "profit": 0,
            "comment": "entry",
            "time": same_time,
            "time_msc": 1_786_704_000_123,
        },
        {
            "ticket": "11",
            "order": "2",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 0,
            "profit": 0,
            "comment": "entry",
            "time": same_time,
            "time_msc": 1_786_704_000_123,
        },
        {
            "ticket": "1",
            "order": "1",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 1,
            "profit": 1,
            "comment": "[sl]",
            "time": "2026-08-14T10:00:00.124Z",
            "time_msc": 1_786_704_000_124,
        },
    ]
    events = reconcile_new_deals(deals, ReconcileCursor())
    assert [event.ticket for event in events] == ["002", "11", "1"]
    assert events[-1].time_msc == 1_786_704_000_124


def test_reconcile_rejects_nonfinite_pnl_without_advancing_cursor():
    cursor = ReconcileCursor(processed_tickets={"prior"}, newest_time="2026-08-14T09:00:00Z")
    deals = [
        {
            "ticket": "12",
            "order": "22",
            "position": "30",
            "symbol": "EURUSD",
            "entry": 1,
            "profit": "nan",
            "comment": "[sl]",
            "time": "2026-08-14T10:00:00Z",
        }
    ]
    with pytest.raises(ValueError, match="pnl"):
        reconcile_new_deals(deals, cursor)
    assert cursor.dump() == {
        "processed_tickets": ["prior"],
        "newest_time": "2026-08-14T09:00:00Z",
    }


@pytest.mark.parametrize(
    "deals",
    [
        [
            {
                "ticket": "0",
                "order": "20",
                "symbol": "EURUSD",
                "entry": 0,
                "profit": 0,
                "time": "2026-08-14T10:00:00Z",
            }
        ],
        [
            {
                "ticket": "10",
                "order": "20",
                "position": "30",
                "symbol": "EURUSD",
                "entry": 0,
                "profit": 0,
                "time": "2026-08-14T10:00:00Z",
            },
            {
                "ticket": "10",
                "order": "21",
                "position": "30",
                "symbol": "EURUSD",
                "entry": 1,
                "profit": 1,
                "time": "2026-08-14T10:01:00Z",
            },
        ],
    ],
)
def test_reconcile_rejects_invalid_or_duplicate_ticket_identity_transactionally(deals):
    cursor = ReconcileCursor(
        processed_tickets={"prior"}, newest_time="2026-08-14T09:00:00Z"
    )
    with pytest.raises(ValueError, match="ticket"):
        reconcile_new_deals(deals, cursor)
    assert cursor.dump() == {
        "processed_tickets": ["prior"],
        "newest_time": "2026-08-14T09:00:00Z",
    }


def test_cursor_json_is_atomic_exact_and_transactionally_validated(tmp_path: Path):
    path = tmp_path / "deal_cursor.json"
    cursor = ReconcileCursor(
        processed_tickets={"10", "2"}, newest_time="2026-08-14T10:00:00.123Z"
    )
    cursor.save_json(path)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "processed_tickets": ["10", "2"],
        "newest_time": "2026-08-14T10:00:00.123Z",
    }
    restored = ReconcileCursor()
    assert restored.load_json(path)
    assert restored.dump() == cursor.dump()
    before = restored.dump()
    path.write_text(json.dumps({**before, "unexpected": True}), encoding="utf-8")
    assert not restored.load_json(path)
    assert restored.dump() == before


def test_cursor_rejects_suppressed_tickets_without_a_history_watermark(tmp_path: Path):
    path = tmp_path / "deal_cursor.json"
    path.write_text(
        json.dumps({"processed_tickets": ["10"], "newest_time": ""}),
        encoding="utf-8",
    )
    cursor = ReconcileCursor()
    assert not cursor.load_json(path)
    with pytest.raises(ValueError, match="watermark"):
        ReconcileCursor(processed_tickets={"10"}).save_json(path)


def test_trade_deal_requires_order_identity_transactionally():
    cursor = ReconcileCursor()
    row = {
        "ticket": "10",
        "order": "0",
        "position": "30",
        "symbol": "EURUSD",
        "entry": 0,
        "time": "2026-08-14T10:00:00Z",
    }
    with pytest.raises(ValueError, match="order"):
        reconcile_new_deals([row], cursor)
    assert cursor.dump() == {"processed_tickets": [], "newest_time": ""}
