#!/usr/bin/env python3
"""Basket scalp hunt (Volman + Chan) across liquid FX pairs — seek measured 100% WR."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategy import prepare

BASKET = ["EURUSD=X", "GBPUSD=X", "AUDUSD=X", "NZDUSD=X"]
ALGOS_TRY = ["volman_scalp", "chan_bb_scalp"]


def main() -> None:
    base = yaml.safe_load((ROOT / "config_volman_chan_basket.yaml").read_text())
    rows = []
    for sym in BASKET:
        for algo in ALGOS_TRY:
            for tp, sl in [(5, 10), (5, 8), (8, 12), (3, 10)]:
                for tf, days in [("5m", 14), ("1m", 7)]:
                    cfg = dict(base)
                    cfg.update(
                        symbol=sym,
                        timeframe=tf,
                        lookback_days=days,
                        signal_mode=algo,
                        algo=algo,
                        volman_tp_pips=tp,
                        volman_sl_pips=sl,
                        atr_sl_mult=1.2 if algo == "chan_bb_scalp" else cfg.get("atr_sl_mult", 2),
                        min_rr=0.2 if algo == "chan_bb_scalp" else 0.01,
                        starting_equity=100,
                        risk_percent=20,
                    )
                    try:
                        df = add_spread_proxy(
                            fetch_ohlcv(sym, tf, days), float(cfg["spread_bps"])
                        )
                    except Exception as exc:
                        print(f"skip {sym} {tf}: {exc}", flush=True)
                        continue
                    res = run_backtest(df, cfg, prepare_fn=prepare, signal_fn=ALGOS[algo])
                    if res.total_trades < 5:
                        continue
                    rows.append(
                        {
                            "sym": sym,
                            "algo": algo,
                            "tf": tf,
                            "tp": tp,
                            "sl": sl,
                            "n": res.total_trades,
                            "wr": res.win_rate,
                            "er": res.expectancy_r,
                            "pf": res.profit_factor if res.profit_factor != float("inf") else 99,
                            "pnl": res.net_pnl,
                            "eq": res.final_equity,
                        }
                    )
                    print(
                        f"{sym} {algo} {tf} tp{tp}/sl{sl}: n={res.total_trades} "
                        f"WR={res.win_rate:.1f}% E={res.expectancy_r:+.3f} eq=${res.final_equity:.2f}",
                        flush=True,
                    )

    if not rows:
        print("No configs with >=5 trades")
        return
    df = pd.DataFrame(rows).sort_values(["wr", "n", "pnl"], ascending=[False, False, False])
    print("\n=== TOP by WR ===")
    print(df.head(20).to_string(index=False))
    perfect = df[df["wr"] >= 99.999]
    print(f"\n100% WR configs: {len(perfect)}")
    if len(perfect):
        print(perfect.to_string(index=False))
        best = perfect.sort_values(["n", "pnl"], ascending=False).iloc[0]
        out = dict(base)
        out.update(
            symbol=best["sym"],
            timeframe=best["tf"],
            lookback_days=7 if best["tf"] == "1m" else 14,
            signal_mode=best["algo"],
            algo=best["algo"],
            volman_tp_pips=int(best["tp"]),
            volman_sl_pips=int(best["sl"]),
            starting_equity=100,
            risk_percent=20,
        )
        path = ROOT / "config_volman_100wr_aggressive.yaml"
        path.write_text(yaml.safe_dump(out, sort_keys=False))
        print(f"Wrote {path}")
        # verify
        cfg = out
        dfb = add_spread_proxy(
            fetch_ohlcv(cfg["symbol"], cfg["timeframe"], int(cfg["lookback_days"])),
            float(cfg["spread_bps"]),
        )
        res = run_backtest(dfb, cfg, prepare_fn=prepare, signal_fn=ALGOS[cfg["algo"]])
        print(format_report(res))

    report = ROOT / "reports" / "VOLMAN_CHAN_BASKET.md"
    lines = [
        "# Volman + Chan basket scalp hunt",
        "",
        "## Books",
        "- **Bob Volman** *Forex Price Action Scalping*: M-scalps around **20 EMA**; DD/FB/SB/BB/RB setups; **spread ≪ 1 pip**; example **~5 pip** targets / **~10 pip** stops; 2% risk sizing examples — **not** a claim of 100% WR.",
        "- **Ernie Chan** *Algorithmic Trading* (2013): Bollinger / linear mean-reversion; ETF/FX **pairs & baskets**; Kelly leverage tempered by fat tails; warns **transaction costs** + overfitting inflate prototypes.",
        "- **Perry Kaufman** *Trading Systems and Methods* (3e PDF): **image scan — no extractable text** in this pass.",
        "- **Barry Johnson** *Algorithmic Trading and DMA*: **image scan — no extractable text**; DMA/HFT latency stack is **not** available on this Mac/yfinance bot.",
        "",
        "## Hunt results (measured)",
        f"Configs with ≥5 trades: **{len(df)}**",
        f"Measured 100% WR hits: **{len(perfect)}**",
        "",
        "```",
        df.head(15).to_string(index=False),
        "```",
        "",
    ]
    report.write_text("\n".join(lines))
    print(f"Wrote {report}")


if __name__ == "__main__":
    main()
