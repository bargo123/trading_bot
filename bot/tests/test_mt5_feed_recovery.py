from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.feed_recovery import recover_stalled_feed
from scripts.diagnose_mt5_feed import (
    classify_tick_sources,
    raw_tick_record,
    source_series_advancing,
)


def test_copy_ticks_newer_than_symbol_info_tick_is_python_cache_desync():
    assert classify_tick_sources(
        symbol_time_utc_s=100.0,
        copy_time_utc_s=103.0,
        now_s=103.5,
        stale_after_s=5.0,
    ) == "MT5_PYTHON_TICK_CACHE_DESYNC"


def test_future_copy_timestamp_is_reported_as_timestamp_failure():
    assert classify_tick_sources(
        symbol_time_utc_s=100.0,
        copy_time_utc_s=200.0,
        now_s=103.0,
        stale_after_s=5.0,
    ) == "TIMESTAMP_STILL_WRONG"


def test_both_tick_sources_old_is_broker_feed_stalled():
    assert classify_tick_sources(
        symbol_time_utc_s=90.0,
        copy_time_utc_s=91.0,
        now_s=103.0,
        stale_after_s=5.0,
    ) == "BROKER_FEED_STALLED"


def test_copy_ticks_advancing_requires_newest_timestamp_to_advance():
    assert source_series_advancing([100.0, 100.0, 101.0]) is True
    assert source_series_advancing([100.0, 100.0, 100.0]) is False


def test_standalone_sample_preserves_raw_tick_fields():
    class Api:
        def symbol_info_tick(self, symbol: str) -> object:
            return SimpleNamespace(
                time=1700000000,
                time_msc=1700000000123,
                bid=1.1,
                ask=1.1002,
                last=0.0,
                flags=1030,
            )

        def last_error(self) -> tuple[int, str]:
            return (1, "Success")

    record = raw_tick_record(
        Api(), requested_symbol="EURUSD", resolved_symbol="EURUSD.a", local_now_s=1700000001.0
    )

    assert record["resolved_symbol"] == "EURUSD.a"
    assert record["tick"]["time_msc"] == 1700000000123
    assert record["tick"]["bid"] == 1.1


def test_bounded_recovery_refreshes_then_reinitializes_once_and_recovers():
    class StubEngine:
        def __init__(self) -> None:
            self.refresh_calls: list[list[str]] = []
            self.reinitialize_calls = 0
            self.restarted = False
            self.raw_calls = 0

        def raw_tick(self, symbol: str) -> dict[str, object]:
            self.raw_calls += 1
            advanced = self.restarted and self.raw_calls > 4
            return {
                "resolved_symbol": symbol,
                "time_msc": 2000 if advanced else 1000,
                "bid": 1.1002 if advanced else 1.1000,
                "ask": 1.1003 if advanced else 1.1001,
            }

        def refresh_symbols(self, symbols: list[str]) -> int:
            self.refresh_calls.append(list(symbols))
            return len(symbols)

        def reinitialize_connection(self, *, symbols: list[str], backoff_s: float) -> dict[str, object]:
            self.reinitialize_calls += 1
            self.restarted = True
            return {"symbols": list(symbols), "backoff_s": backoff_s}

    clock = [0.0]

    def monotonic() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    engine = StubEngine()
    result = recover_stalled_feed(
        engine,
        ["EURUSD", "GBPUSD"],
        probe_seconds=0.2,
        poll_seconds=0.1,
        reconnect_backoff_s=0.5,
        monotonic_fn=monotonic,
        sleep_fn=sleep,
    )

    assert result.success is True
    assert result.stage == "REINITIALIZE"
    assert result.advanced_symbols == ["EURUSD", "GBPUSD"]
    assert engine.refresh_calls == [["EURUSD", "GBPUSD"]]
    assert engine.reinitialize_calls == 1


def test_bounded_recovery_fails_closed_when_raw_tick_is_unavailable():
    class NoRawEngine:
        def refresh_symbols(self, symbols: list[str]) -> int:
            return len(symbols)

    result = recover_stalled_feed(NoRawEngine(), ["EURUSD"], probe_seconds=0.0)

    assert result.success is False
    assert result.status == "RECOVERY_FAILED"
    assert result.reason == "raw_tick_unavailable"
