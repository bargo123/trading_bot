"""Holdout governance, tick replay, MTF, TPO, protected YAML."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from aegis.config import dump_config, load_config
from aegis.optimizer.promote import promote_if_flat
from aegis.research.dataplane import ticks_frame
from aegis.research.gates import GateReject
from aegis.research.govern import governed_accept
from aegis.research.mtf import mtf_state, require_htf
from aegis.research.profile import tpo_profile
from aegis.research.replay import m1_from_ticks
from aegis.research.stress import bootstrap_expectancy, family_wise_ok, holm_adjusted


def _ticks(n: int = 90) -> pd.DataFrame:
    rows = []
    t0 = datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    for i in range(n):
        ts = t0 + pd.Timedelta(seconds=2 * i)
        rows.append(
            {
                "symbol": "EURUSD",
                "ts_utc": ts.isoformat(),
                "ts_ms": i,
                "seq": i,
                "bid": 1.10 + i * 1e-6,
                "ask": 1.10002 + i * 1e-6,
                "last": 1.10 + i * 1e-6,
                "tick_volume": 1,
                "flags": "",
            }
        )
    return ticks_frame(rows)


def test_replay_drops_incomplete_last_minute():
    ticks = _ticks(90)  # 3 minutes of 2s ticks, last minute incomplete if 90*2s=180s = 3.0 min
    m1 = m1_from_ticks(ticks)
    last_tick = pd.to_datetime(ticks["ts_utc"].iloc[-1], utc=True)
    assert m1["time"].iloc[-1] + pd.Timedelta(minutes=1) <= last_tick


def test_mtf_uses_completed_higher_timeframes():
    t = pd.date_range("2026-01-05", periods=400, freq="min", tz="UTC")
    close = 1.10 + pd.Series(range(400)).astype(float) * 0.00001
    m1 = pd.DataFrame(
        {
            "time": t,
            "open": close,
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "volume": 100,
        }
    )
    state = mtf_state(m1)
    assert require_htf(state, "M5", "M15", "H1")
    assert state["H1"]["n"] >= 6
    assert state["lookahead"] is False


def test_tpo_profile_is_proxy_not_pit():
    t = pd.date_range("2026-01-05", periods=200, freq="min", tz="UTC")
    close = 1.10 + pd.Series(range(200)).astype(float) * 0.00001
    m1 = pd.DataFrame(
        {
            "time": t,
            "open": close,
            "high": close + 0.0002,
            "low": close - 0.0002,
            "close": close,
            "volume": 100,
        }
    )
    prof = tpo_profile(m1)
    assert prof["ok"] is True
    assert prof["pit_session"] is False
    assert prof["order_flow"] is False
    assert prof["va_high"] >= prof["va_low"]


def test_bootstrap_and_holm_do_not_invent_trades():
    pnls = [0.2] * 30 + [-0.05] * 10
    boot = bootstrap_expectancy(pnls, n_boot=500, seed=2)
    assert boot["n"] == 40
    assert boot["mean"] > 0
    adj = holm_adjusted([0.01, 0.04, 0.20])
    assert adj[0] <= adj[1] <= 1.0
    assert family_wise_ok(0.01, n_searches=2, alpha=0.05)
    assert not family_wise_ok(0.04, n_searches=2, alpha=0.05)


def test_governed_accept_rejects_negative_bootstrap_tail():
    pnls = [0.01] * 10 + [-0.5] * 20
    with pytest.raises(GateReject):
        governed_accept(
            {
                "expectancy": 0.02,
                "profit_factor": 1.2,
                "n_trades": 30,
                "net_pnl": 1.0,
                "win_rate": 0.33,
            },
            None,
            pnls=pnls,
            n_searches=1,
        )


def test_governed_accept_rejects_undersampled_loss_tail():
    """40 wins and one small loss on a 1:30 payoff is an unsampled tail, not an edge."""
    pnls = [0.005] * 40 + [-0.02]
    with pytest.raises(GateReject, match="loss"):
        governed_accept(
            {
                "expectancy": 0.0048,
                "profit_factor": 10.98,
                "n_trades": 41,
                "net_pnl": 0.196,
                "win_rate": 0.9756,
            },
            None,
            pnls=pnls,
            n_searches=32,
        )


def test_governed_accept_survives_when_losses_are_sampled():
    pnls = [0.2] * 30 + [-0.05] * 10
    governed_accept(
        {
            "expectancy": 0.14,
            "profit_factor": 12.0,
            "n_trades": 40,
            "net_pnl": 5.5,
            "win_rate": 0.75,
        },
        None,
        pnls=pnls,
        n_searches=1,
    )


def test_tail_stress_needs_edge_to_survive_one_more_loss():
    from aegis.research.stress import tail_stress

    fragile = tail_stress([0.005] * 40 + [-0.02], worst_case_loss=0.30)
    assert fragile["n_losses"] == 1
    assert fragile["expectancy_after_one_more_loss"] < 0

    robust = tail_stress([0.2] * 30 + [-0.05] * 10)
    assert robust["n_losses"] == 10
    assert robust["expectancy_after_one_more_loss"] > 0


def test_champion_can_be_demoted_when_it_was_an_artifact(tmp_path: Path):
    from aegis.research.champion import ChampionStore

    store = ChampionStore(tmp_path / "e.sqlite")
    row = {
        "id": "exp_artifact",
        "hypothesis": "high wr tail artifact",
        "config_fingerprint": "cfg1",
        "dataset_fingerprint": "ds1",
        "expectancy": 0.0048,
        "profit_factor": 10.98,
        "n_trades": 41,
        "net_pnl": 0.196,
        "win_rate": 0.9756,
    }
    store.promote(row)
    assert store.current()["id"] == "exp_artifact"
    store.demote("unsampled loss tail on 1:30 payoff")
    assert store.current() is None
    assert store.registry.get("exp_artifact") is not None


def test_promote_refuses_active_firehose_yaml(tmp_path: Path, monkeypatch):
    accepted = tmp_path / "accepted.yaml"
    live = tmp_path / "config_mt5_demo_firehose_hw.yaml"
    dump_config({"symbol": "EURUSD", "allow_live": False, "timeframe": "1m", "mode": "mt5_demo"}, accepted)
    dump_config(
        {
            "symbol": "EURUSD",
            "timeframe": "1m",
            "mode": "mt5_demo",
            "firehose_tp_pips": 1,
            "allow_live": False,
        },
        live,
    )
    monkeypatch.setattr(
        "aegis.optimizer.promote.load_heartbeat",
        lambda path=None: {"open": 0, "pid": 1},
    )
    result = promote_if_flat(live_config=live, accepted=accepted, restart=False)
    assert result["promoted"] is False
    assert "firehose" in result["message"].lower()
    assert float(load_config(live)["firehose_tp_pips"]) == 1.0
