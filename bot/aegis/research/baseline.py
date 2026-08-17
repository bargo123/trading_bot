"""Costed replay of the live firehose 1/30 geometry as a named benchmark only."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aegis.backtest import run_backtest


BENCHMARK_NAME = "legacy_firehose_1_30"


def firehose_benchmark_config() -> dict[str, Any]:
    return {
        "symbol": "EURUSD",
        "timeframe": "1m",
        "mode": "mt5_demo",
        "allow_live": False,
        "signal_mode": "firehose",
        "firehose_every_bar": False,
        "firehose_tp_pips": 1,
        "firehose_sl_pips": 30,
        "starting_equity": 100,
        "spread_bps": 0.2,
        "slippage_bps": 0.1,
        "commission_bps": 0.0,
        "max_daily_loss_percent": 2,
        "max_total_drawdown_percent": 10,
        "max_positions": 8,
        "risk_percent": 0.25,
        "session_start_utc": 0,
        "session_end_utc": 24,
    }


def replay_firehose_benchmark(df: pd.DataFrame, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    config = firehose_benchmark_config() if cfg is None else dict(cfg)
    result = run_backtest(df, config)
    return {
        "name": BENCHMARK_NAME,
        "label": "benchmark",
        "not_a_champion": True,
        "win_rate": float(result.win_rate),
        "expectancy_r": float(result.expectancy_r),
        "profit_factor": float(result.profit_factor) if result.profit_factor == result.profit_factor else None,
        "net_pnl": float(result.net_pnl),
        "total_trades": int(result.total_trades),
        "max_drawdown_pct": float(result.max_drawdown_pct),
        "costs_applied": True,
    }
