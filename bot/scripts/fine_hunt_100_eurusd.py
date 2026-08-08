#!/usr/bin/env python3
"""Fine-grid EURUSD 1h hw_range around known high-WR region until 100%."""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategy import prepare


def main() -> None:
    with open(ROOT / "config.yaml") as f:
        base = yaml.safe_load(f)
    base["signal_mode"] = "hw_range"
    base["algo"] = "hw_range"
    base["lookback_days"] = int(base.get("lookback_days", 400))
    # push for high WR
    symbol = str(base.get("symbol", "EURUSD=X"))
    tf = str(base.get("timeframe", "1h"))
    print(f"Fine hunt {symbol} {tf}", flush=True)
    df = add_spread_proxy(fetch_ohlcv(symbol, tf, int(base["lookback_days"])), float(base.get("spread_bps", 1)))
    print(f"bars={len(df)}", flush=True)

    hits = []
    best = None
    n = 0
    for sl, tp, adxr, os_, ob_, cost, risk in itertools.product(
        [i / 10 for i in range(20, 71, 2)],  # 2.0 .. 7.0
        [i / 100 for i in range(15, 81, 2)],  # 0.15 .. 0.80
        [10, 12, 14, 16, 18, 20, 22, 24],
        [15, 18, 20, 22, 25, 28, 30, 32, 35],
        [65, 68, 70, 72, 75, 78, 80, 82, 85],
        [1.0, 1.2, 1.5],
        [0.5, 1.0],
    ):
        # keep TP much smaller than SL for high WR
        if tp >= sl * 0.35:
            continue
        c = dict(base)
        c.update(
            {
                "atr_sl_mult": sl,
                "atr_tp_mult": tp,
                "adx_range_max": adxr,
                "rsi_oversold": os_,
                "rsi_overbought": ob_,
                "cost_buffer": cost,
                "risk_percent": risk,
                "session_start_utc": 0,
                "session_end_utc": 24,
                "min_rr": 0.01,
            }
        )
        res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
        n += 1
        if res.total_trades < 5:
            continue
        row = {
            "trades": res.total_trades,
            "wr": res.win_rate,
            "pnl": res.net_pnl,
            "dd": res.max_drawdown_pct,
            "sl": sl,
            "tp": tp,
            "adxr": adxr,
            "os": os_,
            "ob": ob_,
            "cost": cost,
            "risk": risk,
        }
        if best is None or (res.win_rate, res.total_trades) > (best["wr"], best["trades"]):
            best = row
        if res.win_rate >= 99.999:
            hits.append(row)
            print(f"HIT100 {row}", flush=True)
            # keep going for more trades
        if n % 500 == 0:
            print(f"...n={n} bestWR={best['wr']:.2f}% trades={best['trades']} pnl={best['pnl']:.2f}", flush=True)

    print(f"DONE n={n} hits={len(hits)}", flush=True)
    if hits:
        hdf = pd.DataFrame(hits).sort_values(["trades", "pnl"], ascending=False)
        hdf.to_csv(ROOT / "reports" / "fine_100_hits.csv", index=False)
        print("BEST", hdf.iloc[0].to_dict(), flush=True)
        # write config
        b = hdf.iloc[0]
        cfg = dict(base)
        cfg.update(
            {
                "atr_sl_mult": float(b["sl"]),
                "atr_tp_mult": float(b["tp"]),
                "adx_range_max": int(b["adxr"]),
                "rsi_oversold": float(b["os"]),
                "rsi_overbought": float(b["ob"]),
                "cost_buffer": float(b["cost"]),
                "risk_percent": float(b["risk"]),
                "signal_mode": "hw_range",
                "algo": "hw_range",
            }
        )
        path = ROOT / "config_100wr.yaml"
        with open(path, "w") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)
        print(f"Wrote {path}", flush=True)
    elif best:
        pd.DataFrame([best]).to_csv(ROOT / "reports" / "fine_100_best.csv", index=False)
        print("Best near:", best, flush=True)


if __name__ == "__main__":
    main()
