from pathlib import Path

from aegis.intel.firehose_turnover import (
    FirehoseReentryGuard, TurnoverMetrics, confirmed_close_cleanup, quote_fingerprint,
)
from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata
from scripts.run_broker_paper import reconcile_confirmed_firehose_basket_cleanups


def _meta():
    return create_ticket_metadata(
        ticket="T1", hypothesis_id="hyp", thesis_key="thesis", strategy_family="micro",
        expected_mechanism="test", side="buy", entry_price=1.1, stop_loss=1.099,
        target_price=1.102, max_hold_s=120, regime="trend", session="london",
        symbol="EURUSD",
    )


def test_successful_close_releases_metadata_and_records_reentry(tmp_path: Path):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    store.add(_meta())
    guard = FirehoseReentryGuard()
    result = confirmed_close_cleanup(store, guard, "T1", quote_fingerprint="quote-a", closed_at=100.0)
    assert result.metadata_removed is True
    assert store.get("T1") is None
    assert guard.allows("thesis", "quote-a", 101.0) == (False, "stale_reentry")


def test_failed_close_does_not_release_metadata_or_record_reentry(tmp_path: Path):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    store.add(_meta())
    guard = FirehoseReentryGuard()
    result = confirmed_close_cleanup(store, guard, "T1", quote_fingerprint="quote-a", closed_at=100.0, confirmed=False)
    assert result.metadata_removed is False
    assert store.get("T1") is not None
    assert guard.allows("thesis", "quote-a", 101.0)[0] is True


def test_confirmed_close_without_tracked_metadata_does_not_release_slot(tmp_path: Path):
    result = confirmed_close_cleanup(
        TicketMetadataStore(tmp_path / "tickets.json"), FirehoseReentryGuard(), "missing",
        quote_fingerprint="quote-a", closed_at=100.0,
    )
    assert result.metadata_removed is False
    assert result.slot_released is False


def test_ticket_metadata_save_failure_keeps_close_cleanup_recoverable(tmp_path: Path, monkeypatch):
    metadata_path = tmp_path / "tickets.json"
    store = TicketMetadataStore(metadata_path)
    store.add(_meta())
    store.begin_pending_cleanup("T1", {
        "quote_fingerprint": "quote-a", "closed_at": 100.0, "basket_removed": True,
    })
    guard_path = tmp_path / "firehose_reentry_guard.json"
    guard = FirehoseReentryGuard(guard_path)

    monkeypatch.setattr(TicketMetadataStore, "_save", lambda self: False)
    result = confirmed_close_cleanup(store, guard, "T1", quote_fingerprint="quote-a", closed_at=100.0)

    assert result.metadata_removed is False
    assert result.slot_released is False
    assert store.get("T1") is not None
    assert FirehoseReentryGuard(guard_path).allows("thesis", "quote-a", 101.0) == (False, "stale_reentry")

    monkeypatch.undo()
    restored_store = TicketMetadataStore(metadata_path)
    restored_guard = FirehoseReentryGuard(guard_path)
    assert restored_store.get("T1") is not None
    assert restored_store.pending_cleanup("T1") is not None
    retried = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=restored_store,
        guard=restored_guard,
        positions=[],
        contract_for_symbol=lambda symbol: None,
        closed_at=101.0,
    )

    assert retried == [{"ticket_id": "T1", "status": "CLEANED", "basket_removal": {"status": "NO_EVIDENCE"}}]
    assert TicketMetadataStore(metadata_path).get("T1") is None


def test_reentry_guard_save_failure_keeps_metadata_and_slot(tmp_path: Path, monkeypatch):
    metadata_path = tmp_path / "tickets.json"
    store = TicketMetadataStore(metadata_path)
    store.add(_meta())
    store.begin_pending_cleanup("T1", {
        "quote_fingerprint": "quote-a", "closed_at": 100.0, "basket_removed": True,
    })
    guard_path = tmp_path / "firehose_reentry_guard.json"
    guard = FirehoseReentryGuard(guard_path)

    monkeypatch.setattr(FirehoseReentryGuard, "_save", lambda self: False)
    result = confirmed_close_cleanup(store, guard, "T1", quote_fingerprint="quote-a", closed_at=100.0)

    assert result.metadata_removed is False
    assert result.slot_released is False
    assert store.get("T1") is not None
    assert FirehoseReentryGuard(guard_path).allows("thesis", "quote-a", 101.0) == (True, "fresh_quote")

    monkeypatch.undo()
    restored_store = TicketMetadataStore(metadata_path)
    restored_guard = FirehoseReentryGuard(guard_path)
    assert restored_store.get("T1") is not None
    assert restored_store.pending_cleanup("T1") is not None
    retried = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=restored_store,
        guard=restored_guard,
        positions=[],
        contract_for_symbol=lambda symbol: None,
        closed_at=101.0,
    )

    assert retried == [{"ticket_id": "T1", "status": "CLEANED", "basket_removal": {"status": "NO_EVIDENCE"}}]
    assert TicketMetadataStore(metadata_path).get("T1") is None
    assert FirehoseReentryGuard(guard_path).allows("thesis", "quote-a", 101.0) == (False, "stale_reentry")


def test_new_quote_fingerprint_allows_valid_fast_reentry():
    guard = FirehoseReentryGuard()
    guard.record_close("T1", "thesis", "quote-a", 100.0)
    assert guard.allows("thesis", "quote-b", 101.0)[0] is True


def test_reentry_guard_survives_restart(tmp_path: Path):
    path = tmp_path / "reports" / "firehose_reentry_guard.json"
    FirehoseReentryGuard(path).record_close("T1", "thesis", "quote-a", 100.0)
    restored = FirehoseReentryGuard(path)
    assert restored.allows("thesis", "quote-a", 101.0) == (False, "stale_reentry")
    assert restored.allows("thesis", "quote-b", 101.0) == (True, "fresh_quote")


def test_runner_close_and_entry_share_quote_fingerprint():
    closed = quote_fingerprint("EURUSD", "buy", 1.10000, 1.10020)
    guard = FirehoseReentryGuard()
    guard.record_close("T1", "thesis", closed, 100.0)
    assert guard.allows("thesis", quote_fingerprint("EURUSD", "buy", 1.1, 1.1002), 101.0) == (
        False, "stale_reentry",
    )
    assert guard.allows("thesis", quote_fingerprint("EURUSD", "buy", 1.10001, 1.10021), 101.0) == (
        True, "fresh_quote",
    )


def test_confirmed_turnover_reports_average_loss_erasure_geometry():
    metrics = TurnoverMetrics()
    for ticket, opened, closed, net in (
        ("W1", 0.0, 10.0, 0.5),
        ("W2", 20.0, 30.0, 0.5),
        ("L1", 40.0, 50.0, -1.0),
    ):
        metrics.record_open(ticket, opened_at=opened, slot_capacity=1)
        metrics.record_close(
            ticket,
            closed_at=closed,
            gross_pnl_usd=net,
            net_pnl_usd=net,
            cost_usd=0.0,
            confirmed=True,
        )

    snapshot = metrics.snapshot(now=60.0)

    assert snapshot["average_winner_usd"] == 0.5
    assert snapshot["average_loser_usd"] == -1.0
    assert snapshot["wins_erased_by_avg_loss"] == 2.0
    assert snapshot["p95_loss_usd"] == -1.0


def test_turnover_telemetry_tracks_green_time_and_reconciled_outcome():
    metrics = TurnoverMetrics()
    metrics.record_open("T1", opened_at=0.0, slot_capacity=2)
    metrics.record_exit_trace("T1", observed_at=1.0, mfe_usd=0.0, pnl_usd=-0.01)
    metrics.record_exit_trace("T1", observed_at=4.0, mfe_usd=0.04, pnl_usd=0.04)
    metrics.record_exit_trace("T1", observed_at=6.0, mfe_usd=0.04, pnl_usd=0.02)
    metrics.record_close(
        "T1", closed_at=7.0, gross_pnl_usd=None, net_pnl_usd=None,
        cost_usd=None, confirmed=True, exit_reason="fast_take",
    )

    before_reconcile = metrics.snapshot(now=8.0)
    assert before_reconcile["completed_trades"] == 1
    assert before_reconcile["green_within_5s"] == 1
    assert before_reconcile["resolved_outcomes"] == 0
    assert before_reconcile["win_rate"] is None

    assert metrics.record_realized("T1", net_pnl_usd=0.02) is True
    after_reconcile = metrics.snapshot(now=8.0)
    assert after_reconcile["resolved_outcomes"] == 1
    assert after_reconcile["win_rate"] == 1.0
    assert after_reconcile["profit_factor"] is None
    assert after_reconcile["daily_net"] == 0.02
