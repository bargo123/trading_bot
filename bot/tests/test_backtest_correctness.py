#!/usr/bin/env python3
"""Regression tests for measurement defects found by the Aegis audit."""
from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.data import fetch_ohlcv
from aegis.risk import RiskEngine
from aegis.strategy import Signal, prepare


def _cfg(**overrides):
    cfg = {
        "starting_equity": 100.0,
        "risk_percent": 1.0,
        "max_daily_loss_percent": 3.0,
        "max_total_drawdown_percent": 50.0,
        "max_positions": 1,
        "spread_bps": 0.0,
        "slippage_bps": 0.0,
        "min_atr_pct": 0.0,
    }
    cfg.update(overrides)
    return cfg


def _frame(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time": pd.Timestamp("2024-01-02 10:00", tz="UTC") + pd.Timedelta(minutes=i),
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1.0,
            }
            for i, (o, h, l, c) in enumerate(rows)
        ]
    )


def test_historical_daily_loss_uses_bar_time() -> None:
    risk = RiskEngine(1.0, 3.0, 50.0, 1)
    now = datetime(2020, 1, 2, 12, tzinfo=timezone.utc)
    risk.update(100.0, now=now)
    ok, reason = risk.allow(96.0, 0, now=now)
    assert not ok
    assert "daily_loss" in reason


def test_total_drawdown_halt_persists_across_days() -> None:
    risk = RiskEngine(1.0, 50.0, 10.0, 1)
    day1 = datetime(2020, 1, 2, 12, tzinfo=timezone.utc)
    day2 = datetime(2020, 1, 3, 12, tzinfo=timezone.utc)
    risk.update(100.0, now=day1)
    ok, reason = risk.allow(89.0, 0, now=day1)
    assert not ok and "max_drawdown" in reason
    ok, reason = risk.allow(89.0, 0, now=day2)
    assert not ok and "max_drawdown" in reason


def test_expectancy_r_is_net_of_round_trip_cost() -> None:
    bars = _frame([(100, 100, 100, 100), (100, 100.2, 99.8, 100), (100, 101.2, 99.9, 101)])

    def sig(row, _cfg):
        if row.name == 0:
            return Signal("buy", "test", 100, 99, 101, None, row["time"], "cost_r")
        return None

    res = run_backtest(
        bars,
        _cfg(spread_bps=5.0, slippage_bps=5.0),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=sig,
    )
    assert res.total_trades == 1
    assert abs(float(res.trades.iloc[0]["r"]) - 0.8) < 1e-9
    assert abs(res.expectancy_r - 0.8) < 1e-9


def test_open_position_is_liquidated_at_end() -> None:
    bars = _frame([(100, 100, 100, 100), (100, 100.6, 99.9, 100.5)])

    def sig(row, _cfg):
        if row.name == 0:
            return Signal("buy", "test", 100, 99, 110, None, row["time"], "eof")
        return None

    res = run_backtest(
        bars,
        _cfg(),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=sig,
    )
    assert res.total_trades == 1
    assert res.trades.iloc[0]["outcome"] == "eof"
    assert abs(res.final_equity - 100.5) < 1e-9


def test_all_in_loss_stops_at_bankruptcy() -> None:
    bars = _frame([(100, 100, 100, 100), (100, 100.1, 99.9, 100), (100, 100.1, 98.9, 99)])

    def sig(row, _cfg):
        if row.name == 0:
            return Signal("buy", "test", 100, 99, 101, None, row["time"], "bankruptcy")
        return None

    res = run_backtest(
        bars,
        _cfg(
            risk_percent=100,
            spread_bps=5,
            slippage_bps=5,
            high_risk_safe=False,
            allow_unsafe_high_risk=True,
            hr_risk_max_cap=100,
        ),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=sig,
    )
    assert res.final_equity == 0
    assert res.halt_reason == "bankruptcy"
    assert res.trades.iloc[0]["outcome"] == "bankruptcy"


def test_prepare_is_idempotent() -> None:
    n = 320
    close = 1.1 + np.sin(np.arange(n) / 17.0) * 0.002
    raw = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
            "open": close,
            "high": close + 0.0005,
            "low": close - 0.0005,
            "close": close,
            "volume": np.ones(n),
        }
    )
    cfg = {"signal_mode": "firehose", "ema_fast": 20, "ema_slow": 50}
    once = prepare(raw, cfg)
    twice = prepare(once, cfg)
    assert list(once.columns) == list(twice.columns)
    assert not any(c.endswith("_x") or c.endswith("_y") for c in twice.columns)


def test_intraday_download_does_not_silently_fallback_to_daily() -> None:
    calls: list[str] = []

    def download(*_args, **kwargs):
        calls.append(kwargs["interval"])
        if kwargs["interval"] == "1m":
            return pd.DataFrame()
        idx = pd.DatetimeIndex([pd.Timestamp("2024-01-01", tz="UTC")])
        return pd.DataFrame(
            {"Open": [1.0], "High": [1.1], "Low": [0.9], "Close": [1.0], "Volume": [1]},
            index=idx,
        )

    old = sys.modules.get("yfinance")
    sys.modules["yfinance"] = types.SimpleNamespace(download=download)
    try:
        try:
            fetch_ohlcv("EURUSD=X", "1m", 7)
        except RuntimeError as exc:
            assert "1m" in str(exc)
        else:
            raise AssertionError("intraday failure must not silently become daily bars")
    finally:
        if old is None:
            sys.modules.pop("yfinance", None)
        else:
            sys.modules["yfinance"] = old
    assert calls == ["1m"]


if __name__ == "__main__":
    test_historical_daily_loss_uses_bar_time()
    test_total_drawdown_halt_persists_across_days()
    test_expectancy_r_is_net_of_round_trip_cost()
    test_open_position_is_liquidated_at_end()
    test_all_in_loss_stops_at_bankruptcy()
    test_prepare_is_idempotent()
    test_intraday_download_does_not_silently_fallback_to_daily()
    print("ALL BACKTEST CORRECTNESS TESTS PASSED")
