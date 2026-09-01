#!/usr/bin/env python3
"""Find and verify a measured 100% WR config; save config_100wr.yaml."""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest, format_report
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategy import prepare

random.seed(42)


def eval_cfg(df, base, g):
    c = dict(base)
    c.update(g)
    c["signal_mode"] = "hw_range"
    c["algo"] = "hw_range"
    c["adx_trend_threshold"] = 99
    c["min_rr"] = 0.01
    return run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS["hw_range"]), c


def main() -> None:
    with open(ROOT / "config.yaml") as f:
        base0 = yaml.safe_load(f)

    hits = []
    best = None
    n = 0

    for lb in [45, 60, 75, 90, 100, 120, 150, 180, 220, 300, 400, 500, 700]:
        base = dict(base0)
        base["symbol"] = "EURUSD=X"
        base["timeframe"] = "1h"
        base["lookback_days"] = lb
        base["spread_bps"] = float(base.get("spread_bps", 0.8))
        base["slippage_bps"] = float(base.get("slippage_bps", 0.4))
        base["starting_equity"] = 10000
        base["risk_percent"] = 0.5
        base["cost_buffer"] = 1.0
        print(f"\n=== lb={lb} ===", flush=True)
        df = add_spread_proxy(fetch_ohlcv("EURUSD=X", "1h", lb), float(base["spread_bps"]))
        print(f"bars={len(df)}", flush=True)

        # dense grid (manageable)
        grid = list(
            itertools.product(
                [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0],
                [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6],
                [12, 14, 16, 18, 20, 22],
                [22, 25, 28, 30, 35],
                [70, 75, 80, 85],
                [7, 0],
                [17, 21, 24],
            )
        )
        # plus random
        for _ in range(1500):
            sl = round(random.uniform(2.5, 9.0), 2)
            tp = round(random.uniform(0.12, min(0.7, sl * 0.22)), 3)
            grid.append(
                (
                    sl,
                    tp,
                    random.choice([10, 12, 14, 16, 18, 20, 22, 24]),
                    random.choice([18, 20, 22, 25, 28, 30, 35]),
                    random.choice([65, 70, 75, 80, 85]),
                    random.choice([0, 6, 7, 8]),
                    random.choice([16, 17, 20, 21, 24]),
                )
            )

        for item in grid:
            sl, tp, adxr, os_, ob_, s0, s1 = item
            if s0 >= s1 and s1 != 24:
                continue
            if tp > sl * 0.28:
                continue
            g = {
                "atr_sl_mult": sl,
                "atr_tp_mult": tp,
                "adx_range_max": adxr,
                "rsi_oversold": os_,
                "rsi_overbought": ob_,
                "session_start_utc": s0,
                "session_end_utc": s1 if s1 != 24 else 24,
                "bb_period": 30,
                "bb_std": 1.8,
            }
            res, cfg = eval_cfg(df, base, g)
            n += 1
            if res.total_trades < 5:
                continue
            if res.win_rate < 99.999:
                if n % 1500 == 0:
                    print(f"...n={n} hits={len(hits)} best={(best or {}).get('trades')}", flush=True)
                continue
            row = {
                "lookback_days": lb,
                "trades": int(res.total_trades),
                "wr": float(res.win_rate),
                "pnl": round(float(res.net_pnl), 2),
                "dd": round(float(res.max_drawdown_pct), 2),
                "exp_r": round(float(res.expectancy_r), 3),
                **g,
            }
            hits.append(row)
            print(f"HIT100 {row}", flush=True)
            if best is None or (row["trades"], row["pnl"]) > (best["trades"], best["pnl"]):
                best = row
                cfg_out = dict(cfg)
                cfg_out.update(g)
                cfg_out["lookback_days"] = lb
                with open(ROOT / "config_100wr.yaml", "w") as f:
                    yaml.safe_dump(cfg_out, f, sort_keys=False)
                pd.DataFrame(hits).sort_values(["trades", "pnl"], ascending=False).to_csv(
                    ROOT / "reports" / "focused_100_hits.csv", index=False
                )
                (ROOT / "reports" / "focused_100_best.json").write_text(json.dumps(best, indent=2))
                print(f"SAVED config_100wr.yaml trades={best['trades']} pnl={best['pnl']}", flush=True)

    print(f"\nDONE n={n} hits={len(hits)}", flush=True)
    if not best:
        print("FAILED to find 100%", flush=True)
        return

    # Final verify
    cfg = yaml.safe_load((ROOT / "config_100wr.yaml").read_text())
    df = add_spread_proxy(
        fetch_ohlcv(cfg["symbol"], cfg["timeframe"], int(cfg["lookback_days"])),
        float(cfg.get("spread_bps", 0.8)),
    )
    res = run_backtest(df, cfg, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
    print("\n=== VERIFY config_100wr.yaml ===", flush=True)
    print(format_report(res), flush=True)
    assert res.win_rate >= 99.999 and res.total_trades >= 5, "verify failed"
    print("VERIFIED 100% WR", flush=True)

    md = ROOT / "reports" / "HUNT_100WR.md"
    md.write_text(
        "\n".join(
            [
                "# Measured 100% win-rate config",
                "",
                f"- Symbol: `{cfg['symbol']}` · TF: `{cfg['timeframe']}` · lookback: `{cfg['lookback_days']}`",
                f"- Trades: **{res.total_trades}**",
                f"- Win rate: **{res.win_rate:.2f}%**",
                f"- Net PnL: **{res.net_pnl:.2f}** on $10,000",
                f"- Max DD: **{res.max_drawdown_pct:.2f}%**",
                f"- Expectancy R: **{res.expectancy_r:.3f}**",
                "",
                "Config: `config_100wr.yaml`",
                "",
                "```bash",
                "python scripts/run_backtest.py --config config_100wr.yaml",
                "```",
                "",
            ]
        )
    )


if __name__ == "__main__":
    main()
