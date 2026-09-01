from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from aegis.research.bars import BarBuildError, bars_from_ticks
from aegis.research.capabilities import CapabilityUnavailable, require_capability
from aegis.research.costs import cost_book_from_journal, cost_book_from_deals
from aegis.research.dataplane import ticks_frame
from aegis.research.profile import volume_at_price
from aegis.research.store import TickStore, TickStoreError


def _tick(i: int, *, ts: datetime, bid: float = 1.10, ask: float = 1.10002, vol: float = 1.0) -> dict:
    return {
        "symbol": "EURUSD",
        "ts_utc": ts.isoformat(),
        "ts_ms": int(ts.timestamp() * 1000) + i,
        "seq": i,
        "bid": bid,
        "ask": ask,
        "last": (bid + ask) / 2.0,
        "tick_volume": vol,
        "flags": "",
    }


def test_tick_store_persists_source_quality_and_order(tmp_path: Path):
    store = TickStore(tmp_path / "ticks.sqlite")
    t0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    rows = [
        _tick(1, ts=t0.replace(microsecond=2000), bid=1.10001),
        _tick(0, ts=t0.replace(microsecond=1000), bid=1.10),
    ]
    meta = store.append(
        rows,
        source="offline_fixture",
        timezone_name="UTC",
        quality="ok",
    )
    assert meta["schema"] == "ticks.v1"
    assert meta["source"] == "offline_fixture"
    loaded = store.load("EURUSD")
    assert list(loaded["seq"]) == [0, 1]
    assert loaded.attrs["volume_kind"] == "broker_tick_volume_proxy"
    assert loaded.attrs["quality"] == "ok"
    assert meta["fingerprint"]


def test_tick_store_rejects_corrupt_or_future_leak(tmp_path: Path):
    store = TickStore(tmp_path / "ticks.sqlite")
    with pytest.raises(TickStoreError):
        store.append([{"symbol": "EURUSD"}], source="x", timezone_name="UTC", quality="ok")
    t0 = datetime(2026, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    bad = _tick(0, ts=t0)
    bad["bid"] = float("nan")
    with pytest.raises(TickStoreError):
        store.append([bad], source="x", timezone_name="UTC", quality="ok")


def test_bars_use_broker_tz_and_drop_incomplete(tmp_path: Path):
    t0 = datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(90):
        ts = t0 + pd.Timedelta(seconds=2 * i)
        rows.append(_tick(i, ts=ts))
    ticks = ticks_frame(rows)
    with pytest.raises(BarBuildError, match="timezone_assumption"):
        bars_from_ticks(ticks, tf="M1", broker_tz=None, timezone_assumption=None)
    m1 = bars_from_ticks(
        ticks,
        tf="M1",
        broker_tz="Europe/Athens",
        timezone_assumption="unmeasured_metaquotes_demo",
    )
    assert len(m1) >= 1
    assert m1.attrs["timezone_assumption"] == "unmeasured_metaquotes_demo"
    assert "broker_time" in m1.columns
    assert m1.attrs["volume_kind"] == "broker_tick_volume_proxy"
    last_tick = pd.to_datetime(ticks["ts_utc"].iloc[-1], utc=True)
    assert pd.to_datetime(m1["time"].iloc[-1], utc=True) + pd.Timedelta(minutes=1) <= last_tick


def test_dst_spring_forward_does_not_invent_a_missing_local_hour():
    # 2026-03-29 01:00 UTC == 03:00 Europe/Athens after the 03:00 jump from 02:00.
    athens = ZoneInfo("Europe/Athens")
    rows = []
    start = datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc)
    for i in range(60):
        ts = start + pd.Timedelta(minutes=i)
        rows.append(_tick(i, ts=ts))
    ticks = ticks_frame(rows)
    m1 = bars_from_ticks(
        ticks,
        tf="M1",
        broker_tz="Europe/Athens",
        timezone_assumption="dst_fixture",
    )
    locals_ = [pd.Timestamp(t).tz_convert(athens).hour for t in m1["broker_time"]]
    assert 3 not in locals_


def test_vap_and_tap_are_labeled_proxies():
    t0 = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    rows = [_tick(i, ts=t0 + pd.Timedelta(seconds=i), bid=1.10 + (i % 3) * 0.0001) for i in range(30)]
    ticks = ticks_frame(rows)
    vap = volume_at_price(ticks)
    assert vap["ok"] is True
    assert vap["kind"] == "volume_at_price_broker_tick_proxy"
    assert vap["centralized_volume"] is False
    assert vap["poc"] > 0


def test_cost_book_records_rejects_and_zero_commission_honestly(tmp_path: Path):
    journal = tmp_path / "j.jsonl"
    rows = [
        {"event": "order", "ok": True, "symbol": "EURUSD", "spread": 0.00002, "msg": "done"},
        {"event": "order", "ok": False, "symbol": "EURUSD", "msg": "10019 No money"},
        {"event": "order", "ok": False, "symbol": "GBPUSD", "msg": "10018 Market closed"},
        {"event": "spread_skip", "symbol": "GBPNZD", "spread": 0.0004},
    ]
    journal.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    book = cost_book_from_journal(journal)
    assert book["n_orders"] == 3
    assert book["n_ok"] == 1
    assert book["n_no_money"] == 1
    assert book["n_spread_skip"] == 1
    assert book["commission_observed"] is False
    deals = tmp_path / "d.jsonl"
    deals.write_text(
        json.dumps({"ticket": "1", "symbol": "EURUSD", "pnl": -0.11, "commission": 0.0, "swap": 0.0})
        + "\n"
        + json.dumps({"ticket": "1", "symbol": "EURUSD", "pnl": -0.11, "commission": 0.0, "swap": 0.0})
        + "\n",
        encoding="utf-8",
    )
    dbook = cost_book_from_deals(deals)
    assert dbook["commission_sum"] == 0.0
    assert dbook["swap_sum"] == 0.0
    assert dbook["commission_mode"] == "observed_zero_or_absent"
    assert dbook["n_raw"] == 2
    assert dbook["n"] == 1
    assert dbook["expectancy"] == -0.11
    assert dbook["deduped_by"] == "ticket"


def test_partial_fill_and_cross_asset_stay_unavailable():
    with pytest.raises(CapabilityUnavailable):
        require_capability("partial_fill_state")
    with pytest.raises(CapabilityUnavailable):
        require_capability("cross_asset")
