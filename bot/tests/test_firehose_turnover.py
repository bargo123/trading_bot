from pathlib import Path

from aegis.intel.firehose_turnover import FirehoseReentryGuard, confirmed_close_cleanup
from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata


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


def test_new_quote_fingerprint_allows_valid_fast_reentry():
    guard = FirehoseReentryGuard()
    guard.record_close("T1", "thesis", "quote-a", 100.0)
    assert guard.allows("thesis", "quote-b", 101.0)[0] is True
