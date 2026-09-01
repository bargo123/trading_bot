#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest
from aegis.config import load_config
from aegis.data import add_spread_proxy, fetch_ohlcv


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest Aegis multi-regime bot")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = parser.parse_args()
    cfg = load_config(args.config)
    df = fetch_ohlcv(cfg["symbol"], cfg["timeframe"], int(cfg.get("lookback_days", 730)))
    df = add_spread_proxy(df, float(cfg.get("spread_bps", 1.0)))
    print(f"Loaded {len(df)} bars for {cfg['symbol']} {cfg['timeframe']}")
    res = run_backtest(df, cfg)
    print(format_report(res))
    out = ROOT / "reports" / "last_backtest_trades.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not res.trades.empty:
        res.trades.to_csv(out, index=False)
        print(f"Trades saved: {out}")
        print(res.trades.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
