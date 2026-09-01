#!/usr/bin/env python3
"""Random+local search for 100% WR on EURUSD 1h hw_range (fast)."""
from __future__ import annotations

import random
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

random.seed(7)


def sample_params(rng: random.Random) -> dict:
    sl = rng.uniform(2.0, 8.0)
    tp = rng.uniform(0.12, min(0.9, sl * 0.25))
    return {
        "atr_sl_mult": round(sl, 2),
        "atr_tp_mult": round(tp, 3),
        "adx_range_max": rng.choice([10, 12, 14, 16, 18, 20, 22, 24, 26]),
        "rsi_oversold": rng.choice([15, 18, 20, 22, 25, 28, 30, 32, 35]),
        "rsi_overbought": rng.choice([65, 68, 70, 72, 75, 78, 80, 82, 85]),
        "bb_period": rng.choice([20, 24, 28, 30, 34, 40]),
        "bb_std": rng.choice([1.5, 1.6, 1.8, 2.0, 2.2, 2.5]),
        "cost_buffer": rng.choice([1.0, 1.2, 1.5]),
        "risk_percent": rng.choice([0.25, 0.5, 1.0]),
        "session_start_utc": rng.choice([0, 6, 7, 8]),
        "session_end_utc": rng.choice([17, 20, 21, 22, 24]),
        "min_rr": 0.01,
        "adx_trend_threshold": 99,
    }


def main() -> None:
    with open(ROOT / "config.yaml") as f:
        base = yaml.safe_load(f)
    base["signal_mode"] = "hw_range"
    base["algo"] = "hw_range"
    symbol = str(base.get("symbol", "EURUSD=X"))
    tf = str(base.get("timeframe", "1h"))
    lb = int(base.get("lookback_days", 700))
    print(f"Random hunt {symbol} {tf} lb={lb}", flush=True)
    df = add_spread_proxy(fetch_ohlcv(symbol, tf, lb), float(base.get("spread_bps", 0.8)))
    print(f"bars={len(df)}", flush=True)

    hits = []
    best = None
    n = 0
    # also seed around known good
    seeds = [
        {"atr_sl_mult": 3.0, "atr_tp_mult": 0.6, "adx_range_max": 22, "rsi_oversold": 30, "rsi_overbought": 75,
         "bb_period": 30, "bb_std": 1.8, "cost_buffer": 1.0, "risk_percent": 0.5,
         "session_start_utc": 7, "session_end_utc": 21, "min_rr": 0.01, "adx_trend_threshold": 99},
        {"atr_sl_mult": 4.0, "atr_tp_mult": 0.35, "adx_range_max": 18, "rsi_oversold": 25, "rsi_overbought": 75,
         "bb_period": 30, "bb_std": 2.0, "cost_buffer": 1.0, "risk_percent": 0.5,
         "session_start_utc": 7, "session_end_utc": 21, "min_rr": 0.01, "adx_trend_threshold": 99},
        {"atr_sl_mult": 5.0, "atr_tp_mult": 0.25, "adx_range_max": 16, "rsi_oversold": 25, "rsi_overbought": 80,
         "bb_period": 28, "bb_std": 2.0, "cost_buffer": 1.0, "risk_percent": 0.5,
         "session_start_utc": 0, "session_end_utc": 24, "min_rr": 0.01, "adx_trend_threshold": 99},
        {"atr_sl_mult": 6.0, "atr_tp_mult": 0.2, "adx_range_max": 14, "rsi_oversold": 20, "rsi_overbought": 80,
         "bb_period": 34, "bb_std": 2.2, "cost_buffer": 1.0, "risk_percent": 0.5,
         "session_start_utc": 7, "session_end_utc": 20, "min_rr": 0.01, "adx_trend_threshold": 99},
    ]

    queue = list(seeds)
    for _ in range(8000):
        queue.append(sample_params(random))

    for g in queue:
        c = dict(base)
        c.update(g)
        c["signal_mode"] = "hw_range"
        c["algo"] = "hw_range"
        res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
        n += 1
        if res.total_trades < 5:
            # local mutate toward more trades if high wr on tiny - skip
            continue
        row = {"trades": res.total_trades, "wr": res.win_rate, "pnl": res.net_pnl, "dd": res.max_drawdown_pct, **g}
        if best is None or (res.win_rate, res.total_trades, res.net_pnl) > (best["wr"], best["trades"], best["pnl"]):
            best = row
            print(f"NEW BEST wr={row['wr']:.2f}% trades={row['trades']} pnl={row['pnl']:.2f}", flush=True)
            # local hill-climb
            for _ in range(40):
                g2 = dict(g)
                g2["atr_sl_mult"] = round(max(1.5, g2["atr_sl_mult"] + random.uniform(-0.4, 0.8)), 2)
                g2["atr_tp_mult"] = round(max(0.1, min(g2["atr_sl_mult"] * 0.3, g2["atr_tp_mult"] + random.uniform(-0.08, 0.05))), 3)
                c2 = dict(base); c2.update(g2); c2["signal_mode"]="hw_range"; c2["algo"]="hw_range"
                r2 = run_backtest(df, c2, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
                n += 1
                if r2.total_trades >= 5 and (r2.win_rate, r2.total_trades, r2.net_pnl) > (best["wr"], best["trades"], best["pnl"]):
                    best = {"trades": r2.total_trades, "wr": r2.win_rate, "pnl": r2.net_pnl, "dd": r2.max_drawdown_pct, **g2}
                    g = g2
                    print(f"  climb wr={best['wr']:.2f}% trades={best['trades']} pnl={best['pnl']:.2f}", flush=True)
                if r2.total_trades >= 5 and r2.win_rate >= 99.999:
                    hits.append({"trades": r2.total_trades, "wr": r2.win_rate, "pnl": r2.net_pnl, "dd": r2.max_drawdown_pct, **g2})
                    print(f"HIT100 {hits[-1]}", flush=True)
        if res.win_rate >= 99.999 and res.total_trades >= 5:
            hits.append(row)
            print(f"HIT100 {row}", flush=True)
        if n % 400 == 0 and best:
            print(f"...evals={n} bestWR={best['wr']:.2f}% trades={best['trades']}", flush=True)

    print(f"DONE evals={n} hits={len(hits)}", flush=True)
    out = ROOT / "reports"
    if hits:
        hdf = pd.DataFrame(hits).sort_values(["trades", "pnl"], ascending=False)
        hdf.to_csv(out / "random_100_hits.csv", index=False)
        b = hdf.iloc[0]
        print("BEST 100%", b.to_dict(), flush=True)
        cfg = dict(base)
        for k in ["atr_sl_mult","atr_tp_mult","adx_range_max","rsi_oversold","rsi_overbought",
                  "bb_period","bb_std","cost_buffer","risk_percent","session_start_utc","session_end_utc",
                  "min_rr","adx_trend_threshold"]:
            if k in b:
                cfg[k] = b[k].item() if hasattr(b[k], 'item') else b[k]
        cfg["signal_mode"] = "hw_range"
        cfg["algo"] = "hw_range"
        path = ROOT / "config_100wr.yaml"
        with open(path, "w") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)
        print("Wrote", path, flush=True)
    elif best:
        pd.DataFrame([best]).to_csv(out / "random_100_best.csv", index=False)
        print("Best:", best, flush=True)
        # still write best as config_maxwr
        cfg = dict(base)
        for k, v in best.items():
            if k in cfg or k in {"atr_sl_mult","atr_tp_mult","adx_range_max","rsi_oversold","rsi_overbought",
                                  "bb_period","bb_std","cost_buffer","risk_percent","session_start_utc",
                                  "session_end_utc","min_rr","adx_trend_threshold"}:
                cfg[k] = v
        cfg["signal_mode"] = "hw_range"
        cfg["algo"] = "hw_range"
        with open(ROOT / "config_maxwr.yaml", "w") as f:
            yaml.safe_dump(cfg, f, sort_keys=False)


if __name__ == "__main__":
    main()
