#!/usr/bin/env python3
"""Test Fabris NTZ + Fuller pyramiding vs baselines on same data."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.features import enrich_all
from aegis.session_algos import ALGOS
from aegis.strategy import prepare


def base_cfg(symbol: str, timeframe: str) -> dict:
    spr = 2.0 if "BTC" in symbol else 1.0
    if timeframe == "15m":
        lookback = 45
    elif timeframe == "1h":
        lookback = 120
    else:
        lookback = 30
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "lookback_days": lookback,
        "starting_equity": 10000.0,
        "ema_fast": 20,
        "ema_slow": 50,
        "atr_period": 14,
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "adx_period": 14,
        "adx_trend_threshold": 25,
        "donchian_period": 20,
        "spread_bps": spr,
        "slippage_bps": spr * 0.5,
        "min_atr_pct": 0.0,
        "risk_percent": 1.0,
        "max_daily_loss_percent": 6.0,
        "max_total_drawdown_percent": 20.0,
        "max_positions": 1,
        "kill_switch": False,
        "session_start_utc": 7,
        "session_end_utc": 17,
        "atr_sl_mult": 1.5,
        "atr_tp_mult": 2.5,
        "atr_trail_mult": 2.5,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "adx_range_max": 25,
        "adx_min": 20,
        "cost_buffer": 1.5,
        "min_rr": 1.5,
        "orb_bars": 2,
        "ib_bars": 4,
        "ntz_start_utc": 7,
        "ntz_end_utc": 8,
        "ntz_flatten_utc": 17,
        "ntz_min_atr": 0.4,
        "ntz_max_atr": 3.0,
        "ntz_asia_max_pct": 0.03,
        # no ntz_asia_max_atr → pct-only gate
        "ntz_tp_mult": 2.0,
        "ntz_buffer": 0.0,
        "ntz_max_trades_day": 2,
        "pyramid_enabled": False,
        "pyramid_max_adds": 2,
        "pyramid_add_r": 1.0,
        "pyramid_adx_min": 22.0,
        "max_hold_bars": 0,
    }


def main() -> None:
    symbols = ["BTC-USD", "EURUSD=X"]
    timeframe = "15m"
    all_rows = []
    for symbol in symbols:
        cfg = base_cfg(symbol, timeframe)
        if "EUR" in symbol:
            # Fabris pip band ~10–30 pips
            cfg["ntz_min_abs"] = 0.0010
            cfg["ntz_max_abs"] = 0.0030
            cfg["ntz_min_atr"] = 0.2
            cfg["ntz_max_atr"] = 5.0
            cfg["spread_bps"] = 0.8
            cfg["slippage_bps"] = 0.4
            cfg["ntz_asia_max_pct"] = 0.008
        print(f"\n######## {symbol} {timeframe} ########", flush=True)
        try:
            df = add_spread_proxy(
                fetch_ohlcv(symbol, timeframe, int(cfg["lookback_days"])), float(cfg["spread_bps"])
            )
        except Exception as e:
            print(f"SKIP {symbol}: {e}", flush=True)
            continue
        print(f"Bars: {len(df)} | {df['time'].iloc[0]} → {df['time'].iloc[-1]}", flush=True)

        frame = enrich_all(df, cfg)
        need = ["ntz_high", "ntz_low", "ntz_ready", "ntz_break_up", "ntz_break_dn", "ntz_width_ok"]
        missing = [c for c in need if c not in frame.columns]
        if missing:
            raise SystemExit(f"Missing features: {missing}")
        print(
            f"Feature smoke OK | NTZ ready bars={int(frame['ntz_ready'].sum())} "
            f"width_ok={int(frame['ntz_width_ok'].sum())} "
            f"breaks_up={int(frame['ntz_break_up'].sum())} breaks_dn={int(frame['ntz_break_dn'].sum())}",
            flush=True,
        )

        cases = [
            ("fabris_ntz", False, 2.0),
            ("fabris_ntz_pyramid", True, 3.0),
            ("breakout_adx", False, 2.0),
        ]
        for label, pyr, tp_m in cases:
            name = "fabris_ntz" if label.startswith("fabris") else label
            c = dict(cfg)
            c["signal_mode"] = name
            c["algo"] = name
            c["pyramid_enabled"] = pyr
            c["ntz_tp_mult"] = tp_m
            if name != "fabris_ntz":
                c["ntz_flatten_utc"] = None
                c["ntz_max_trades_day"] = 0
                c["session_start_utc"] = 0
                c["session_end_utc"] = 24
            res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS[name])
            adds = 0
            if not res.trades.empty and "adds" in res.trades.columns:
                adds = int(res.trades["adds"].sum())
            print(f"\n=== {symbol} · {label} ===", flush=True)
            print(format_report(res), flush=True)
            print(f"Pyramid adds (sum): {adds}", flush=True)
            all_rows.append(
                {
                    "symbol": symbol,
                    "algo": label,
                    "trades": res.total_trades,
                    "win_rate": round(res.win_rate, 2),
                    "profit_factor": None if res.profit_factor == float("inf") else round(res.profit_factor, 3),
                    "max_dd_pct": round(res.max_drawdown_pct, 2),
                    "expectancy_r": round(res.expectancy_r, 3),
                    "net_pnl": round(res.net_pnl, 2),
                    "final_equity": round(res.final_equity, 2),
                    "pyramid_adds": adds,
                }
            )

    if not all_rows:
        raise SystemExit("No results")
    table = pd.DataFrame(all_rows).sort_values(["symbol", "net_pnl"], ascending=[True, False])
    out = ROOT / "reports" / "fabris_fuller_test.csv"
    table.to_csv(out, index=False)
    md = ROOT / "reports" / "FABRIS_FULLER_TEST.md"
    lines = [
        "# Fabris NTZ + Fuller pyramiding wiring test",
        "",
        f"TF: `{timeframe}` · Start equity: `$10,000`",
        "",
        "| Symbol | Algo | Trades | WR% | PF | MaxDD% | Exp R | Net PnL | Final | Adds |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in table.iterrows():
        pf = "inf" if pd.isna(r["profit_factor"]) else f"{r['profit_factor']:.3f}"
        lines.append(
            f"| `{r['symbol']}` | `{r['algo']}` | {r['trades']} | {r['win_rate']:.1f} | {pf} | "
            f"{r['max_dd_pct']:.2f} | {r['expectancy_r']:.3f} | {r['net_pnl']:.2f} | "
            f"{r['final_equity']:.2f} | {r['pyramid_adds']} |"
        )
    lines += [
        "",
        "## Wired from books",
        "- **Fabris NTZ** — GMT 07–08 high/low breakout, width filter, SL=opposite NTZ, TP=N×width, flatten 17:00, ≤2 trades/day",
        "- **Fuller pyramid** — add at +1R/+2R only if ADX strong; trail unified SL to prior entry (risk ≤ 1R)",
        "",
        "Note: sample results are costs-in, no look-ahead; Fabris was designed for FX session structure — BTC is a transfer test.",
        "",
        f"CSV: `{out}`",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n=== RANKED ===", flush=True)
    print(table.to_string(index=False), flush=True)
    print(f"\nReport: {md}", flush=True)


if __name__ == "__main__":
    main()
