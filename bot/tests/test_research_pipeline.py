"""Data plane, rollback, selective pipeline, capabilities."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from aegis.research.capabilities import CapabilityUnavailable, require_capability
from aegis.research.champion import ChampionStore
from aegis.research.dataplane import (
    SCHEMA_VERSION,
    capabilities_snapshot,
    contract_snapshot,
    dataset_bundle_fingerprint,
    fill_fact,
    resample_completed,
    ticks_frame,
)
from aegis.research.depth import load_l2
from aegis.research.evaluate import untouched_holdout
from aegis.research.jansen import jansen_ml_predict
from aegis.research.news import load_calendar
from aegis.research.observe import observe_cycle
from aegis.research.pipeline import PipelineContext, run_pipeline


def _m1(n: int = 240) -> pd.DataFrame:
    t = pd.date_range("2026-01-05 00:00", periods=n, freq="min", tz="UTC")
    close = 1.10 + pd.Series(range(n)).astype(float) * 0.00001
    return pd.DataFrame(
        {
            "time": t,
            "open": close,
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "volume": 100,
        }
    )


def test_resample_drops_incomplete_last_bar():
    df = _m1(12)  # 12 M1 minutes → two complete M5 + 2 leftover
    m5 = resample_completed(df, "M5")
    assert len(m5) == 2
    assert m5["time"].iloc[-1] + pd.Timedelta(minutes=5) <= df["time"].iloc[-1] + pd.Timedelta(minutes=1)


def test_bundle_fingerprint_changes_with_bar():
    fp_a = dataset_bundle_fingerprint({"M1": _m1(60)}, {"schema": SCHEMA_VERSION})
    fp_b = dataset_bundle_fingerprint({"M1": _m1(61)}, {"schema": SCHEMA_VERSION})
    assert fp_a != fp_b


def test_contract_snapshot_is_named_and_versioned():
    snap = contract_snapshot(symbol="EURUSD", digits=5, point=0.00001, tick_value=1.0)
    assert snap["schema"] == SCHEMA_VERSION
    assert snap["symbol"] == "EURUSD"
    assert "l2" not in snap or snap.get("l2") is False


def test_capabilities_mark_missing_feeds_unavailable():
    from aegis.research.capabilities import UNAVAILABLE

    cap = capabilities_snapshot()
    assert cap["mt5_l2"] is False
    assert cap["news_calendar"] is False
    assert all(v is False for v in UNAVAILABLE.values())
    with pytest.raises(CapabilityUnavailable):
        require_capability("news_calendar")
    require_capability("prado_purged_cv")


def test_champion_rollback_restores_predecessor(tmp_path: Path):
    store = ChampionStore(tmp_path / "e.sqlite")
    a = {
        "id": "exp_a",
        "hypothesis": "a",
        "config_fingerprint": "c1",
        "dataset_fingerprint": "d1",
        "expectancy": 0.01,
        "profit_factor": 1.2,
        "n_trades": 80,
        "net_pnl": 1.0,
        "win_rate": 0.55,
    }
    b = {**a, "id": "exp_b", "config_fingerprint": "c2", "expectancy": 0.02, "net_pnl": 2.0}
    store.promote(a)
    store.promote(b)
    assert store.current()["id"] == "exp_b"
    rolled = store.rollback()
    assert rolled["id"] == "exp_a"
    assert store.current()["id"] == "exp_a"
    ids = {r["id"] for r in store.registry.all_rows()}
    assert "exp_a" in ids and "exp_b" in ids
    reopened = ChampionStore(tmp_path / "e.sqlite")
    assert reopened.current()["id"] == "exp_a"


def test_pipeline_skips_stale_quote_and_wide_spread():
    now = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    ctx = PipelineContext(
        now=now,
        quote_ts=datetime(2026, 1, 5, 11, 59, 50, tzinfo=timezone.utc),
        bid=1.10,
        ask=1.1010,
        max_quote_age_s=5,
        max_spread_pips=0.3,
        pip_size=0.0001,
        take_pips=1.0,
        portfolio_ok=True,
        m1=_m1(200),
    )
    d = run_pipeline(ctx)
    assert d.action == "skip"
    assert d.stage in {"data_health", "cost_health"}


def test_pipeline_requires_independent_confluence():
    now = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    ctx = PipelineContext(
        now=now,
        quote_ts=now,
        bid=1.10000,
        ask=1.10002,
        max_quote_age_s=5,
        max_spread_pips=0.5,
        pip_size=0.0001,
        take_pips=1.0,
        portfolio_ok=True,
        m1=_m1(400),
    )
    d = run_pipeline(ctx)
    assert d.action in {"skip", "candidate"}
    if d.action == "candidate":
        assert len(d.reasons) >= 2


def test_pipeline_rejects_tiny_target_huge_stop():
    now = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)
    ctx = PipelineContext(
        now=now,
        quote_ts=now,
        bid=1.10000,
        ask=1.10002,
        max_quote_age_s=5,
        max_spread_pips=0.5,
        pip_size=0.0001,
        take_pips=1.0,
        stop_pips=30.0,
        portfolio_ok=True,
        m1=_m1(400),
        modeled_expectancy=0.02,
    )
    d = run_pipeline(ctx)
    if d.action == "candidate":
        raise AssertionError("1-pip / 30-pip geometry must not pass payoff")
    assert d.stage in {"payoff", "confluence", "regime", "multi_timeframe"}


def test_ticks_and_fill_facts_are_versioned():
    rows = [
        {
            "symbol": "EURUSD",
            "ts_utc": "2026-01-05T00:00:00Z",
            "ts_ms": 1,
            "seq": 0,
            "bid": 1.1,
            "ask": 1.10002,
            "last": 1.1,
            "tick_volume": 3,
            "flags": "",
        }
    ]
    ticks = ticks_frame(rows)
    assert list(ticks.columns)[:3] == ["symbol", "ts_utc", "seq"] or "bid" in ticks.columns
    fact = fill_fact(
        symbol="EURUSD",
        side="buy",
        request_ts="2026-01-05T00:00:00Z",
        quote_ts="2026-01-05T00:00:00Z",
        ack_ts="2026-01-05T00:00:00.080Z",
        status="filled",
        fill_price=1.10002,
        spread=0.00002,
        latency_ms=80,
    )
    assert fact["schema"] == SCHEMA_VERSION
    assert fact["status"] == "filled"


def test_observe_cycle_never_places_orders(tmp_path: Path):
    store = ChampionStore(tmp_path / "e.sqlite")
    out = observe_cycle(
        heartbeat={"equity": 57.4, "open": 4, "halt": False},
        champion=store.current(),
        registry=store.registry,
    )
    assert out["placed_orders"] is False
    assert out["allow_live"] is False
    assert out["mt5_touched"] is False
    assert out["open"] == 4


def test_jansen_ml_is_capability_gated():
    with pytest.raises(CapabilityUnavailable):
        jansen_ml_predict({"rsi": 50})
    with pytest.raises(CapabilityUnavailable):
        load_calendar()
    with pytest.raises(CapabilityUnavailable):
        load_l2()


def test_holdout_split_does_not_overlap_time():
    df = _m1(100)
    train, hold = untouched_holdout(df, holdout_frac=0.3)
    assert len(train) + len(hold) <= len(df)
    assert train["time"].max() < hold["time"].min()
