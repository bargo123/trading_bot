#!/usr/bin/env python3
"""Synthetic shared-equity basket tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.basket_backtest import run_basket_backtest
from aegis.strategy import Signal


def _bars(price: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"time": pd.Timestamp("2024-01-02 10:00", tz="UTC"), "open": price, "high": price, "low": price, "close": price, "volume": 1},
            {"time": pd.Timestamp("2024-01-02 10:01", tz="UTC"), "open": price, "high": price + 0.1, "low": price - 0.1, "close": price, "volume": 1},
            {"time": pd.Timestamp("2024-01-02 10:02", tz="UTC"), "open": price, "high": price + 1.1, "low": price - 0.1, "close": price + 1.0, "volume": 1},
        ]
    )


def _sig(row, _cfg):
    if pd.Timestamp(row["time"]).minute == 0:
        price = float(row["close"])
        return Signal("buy", "test", price, price - 1, price + 1, None, row["time"], "basket")
    return None


def _cfg(**overrides):
    cfg = {
        "starting_equity": 100.0,
        "risk_percent": 1.0,
        "max_daily_loss_percent": 10.0,
        "max_total_drawdown_percent": 50.0,
        "max_positions": 2,
        "spread_bps": 0.0,
        "slippage_bps": 0.0,
        "min_atr_pct": 0.0,
        "max_portfolio_heat_percent": 5.0,
        "max_gross_leverage": 1000.0,
        "min_units": 0.0,
        "unit_step": 0.0,
        "max_currency_exposure": 10,
    }
    cfg.update(overrides)
    return cfg


def test_two_symbols_share_one_equity_curve() -> None:
    data = {"AAAUSD=X": _bars(100.0), "BBBUSD=X": _bars(200.0)}
    res = run_basket_backtest(data, _cfg(), prepare_fn=lambda df, _cfg: df, signal_fn=_sig)
    assert res.total_trades == 2
    assert set(res.trades["symbol"]) == set(data)
    assert abs(res.final_equity - 102.0) < 1e-9


def test_portfolio_position_limit_is_shared() -> None:
    data = {"AAAUSD=X": _bars(100.0), "BBBUSD=X": _bars(200.0)}
    res = run_basket_backtest(
        data,
        _cfg(max_positions=1),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=_sig,
    )
    assert res.total_trades == 1
    assert res.skipped_entries.get("max_positions", 0) == 1


def test_intrabar_exit_cannot_reenter_at_that_bars_open() -> None:
    def signal_each_bar(row, _cfg):
        price = float(row["close"])
        return Signal("buy", "test", price, price - 1, price + 1, None, row["time"], "sequence")

    res = run_basket_backtest(
        {"AAAUSD=X": _bars(100.0)},
        _cfg(),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=signal_each_bar,
    )
    assert res.total_trades == 1


def test_fixed_round_trip_commission_is_charged_once() -> None:
    res = run_basket_backtest(
        {"AAAUSD=X": _bars(100.0)},
        _cfg(commission_round_trip_usd=4.0),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=_sig,
    )
    assert res.total_trades == 1
    assert float(res.trades.iloc[0]["pnl"]) == -3.0
    assert float(res.trades.iloc[0]["fixed_commission_usd"]) == 4.0
    assert res.final_equity == 97.0
    assert res.win_rate == 0.0


def test_signal_price_never_replaces_next_real_open() -> None:
    bars = pd.DataFrame(
        [
            {"time": pd.Timestamp("2024-01-02 10:00", tz="UTC"), "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1},
            {"time": pd.Timestamp("2024-01-02 10:01", tz="UTC"), "open": 101.0, "high": 101.0, "low": 101.0, "close": 101.0, "volume": 1},
            {"time": pd.Timestamp("2024-01-02 10:02", tz="UTC"), "open": 101.0, "high": 103.0, "low": 101.0, "close": 102.0, "volume": 1},
        ]
    )

    def synthetic_signal(row, _cfg):
        if pd.Timestamp(row["time"]).minute == 0:
            return Signal("buy", "ha_test", 999.0, 998.0, 1000.0, None, row["time"], "synthetic")
        return None

    res = run_basket_backtest(
        {"AAAUSD=X": bars},
        _cfg(),
        prepare_fn=lambda df, _cfg: df,
        signal_fn=synthetic_signal,
    )
    assert res.total_trades == 1
    assert float(res.trades.iloc[0]["entry"]) == 101.0
    assert float(res.trades.iloc[0]["sl"]) == 100.0
    assert float(res.trades.iloc[0]["tp"]) == 102.0


if __name__ == "__main__":
    test_two_symbols_share_one_equity_curve()
    test_portfolio_position_limit_is_shared()
    test_intrabar_exit_cannot_reenter_at_that_bars_open()
    test_fixed_round_trip_commission_is_charged_once()
    test_signal_price_never_replaces_next_real_open()
    print("ALL BASKET BACKTEST TESTS PASSED")
