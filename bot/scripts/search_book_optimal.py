#!/usr/bin/env python3
"""
Build + search the book-synthesized `book_optimal` algo.
Tries many parameter grids looking for 100% WR / best expectancy.
Reports honest measured results — does not invent wins.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategy import prepare


def base_cfg(symbol: str, timeframe: str) -> dict:
    spr = 2.0 if "BTC" in symbol else 0.8
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "lookback_days": 45 if timeframe == "15m" else 120,
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
        "min_rr": 2.0,
        "orb_bars": 2 if timeframe == "15m" else 1,
        "ib_bars": 4 if timeframe == "15m" else 2,
        "ntz_start_utc": 7,
        "ntz_end_utc": 8,
        "ntz_flatten_utc": 17,
        "ntz_min_atr": 0.4,
        "ntz_max_atr": 3.0,
        "ntz_asia_max_pct": 0.03 if "BTC" in symbol else 0.008,
        "ntz_tp_mult": 2.0,
        "ntz_max_trades_day": 2,
        "pyramid_enabled": False,
        "squeeze_frac": 0.85,
        "book_min_triggers": 1,
        "book_require_vwap": True,
        "book_adx_max": 45,
        "rsi_pullback": 45,
        "rsi_pullback_hi": 55,
        "max_hold_bars": 0,
        "signal_mode": "book_optimal",
        "algo": "book_optimal",
    }


def grid() -> list[dict]:
    """Parameter search aimed at max WR and max expectancy."""
    rows = []
    for min_rr, need, vwap, adx_min, sl_m, cost_buf in itertools.product(
        [1.0, 1.5, 2.0, 3.0],  # include tight TP (high-WR attempt)
        [1, 2],
        [True, False],
        [18, 25],
        [1.2, 1.5, 2.0],
        [1.2, 2.0],
    ):
        rows.append(
            {
                "min_rr": min_rr,
                "book_min_triggers": need,
                "book_require_vwap": vwap,
                "adx_min": adx_min,
                "atr_sl_mult": sl_m,
                "cost_buffer": cost_buf,
            }
        )
    return rows


def main() -> None:
    symbols = ["EURUSD=X", "BTC-USD"]
    timeframe = "15m"
    all_rows: list[dict] = []
    best_any = None

    for symbol in symbols:
        cfg0 = base_cfg(symbol, timeframe)
        if "EUR" in symbol:
            cfg0["ntz_min_abs"] = 0.0010
            cfg0["ntz_max_abs"] = 0.0030
        print(f"\n######## Fetch {symbol} {timeframe} ########", flush=True)
        df = add_spread_proxy(
            fetch_ohlcv(symbol, timeframe, int(cfg0["lookback_days"])), float(cfg0["spread_bps"])
        )
        print(f"Bars: {len(df)}", flush=True)

        # Baselines
        for name in ["fabris_ntz", "breakout_adx", "aziz_orb", "book_optimal"]:
            c = dict(cfg0)
            c["signal_mode"] = name
            c["algo"] = name
            if name != "book_optimal" and name != "fabris_ntz":
                c["session_start_utc"] = 0
                c["session_end_utc"] = 24
                c["ntz_flatten_utc"] = None
                c["ntz_max_trades_day"] = 0
            res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS[name])
            row = {
                "symbol": symbol,
                "tag": f"baseline:{name}",
                "trades": res.total_trades,
                "win_rate": round(res.win_rate, 2),
                "profit_factor": None if res.profit_factor == float("inf") else round(res.profit_factor, 3),
                "expectancy_r": round(res.expectancy_r, 3),
                "net_pnl": round(res.net_pnl, 2),
                "max_dd_pct": round(res.max_drawdown_pct, 2),
                "final_equity": round(res.final_equity, 2),
                "params": "",
            }
            all_rows.append(row)
            print(
                f"  {name}: trades={res.total_trades} WR={res.win_rate:.1f}% "
                f"PnL={res.net_pnl:.2f} ExpR={res.expectancy_r:.3f}",
                flush=True,
            )
            if best_any is None or res.net_pnl > best_any["net_pnl"]:
                best_any = dict(row)

        # Grid search book_optimal for 100% WR / best PnL
        print(f"  Grid searching book_optimal ({len(grid())} combos)…", flush=True)
        hit_100 = []
        for g in grid():
            c = dict(cfg0)
            c.update(g)
            c["signal_mode"] = "book_optimal"
            c["algo"] = "book_optimal"
            res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS["book_optimal"])
            if res.total_trades < 5:
                continue  # ignore tiny samples claiming "100%"
            row = {
                "symbol": symbol,
                "tag": "search:book_optimal",
                "trades": res.total_trades,
                "win_rate": round(res.win_rate, 2),
                "profit_factor": None if res.profit_factor == float("inf") else round(res.profit_factor, 3),
                "expectancy_r": round(res.expectancy_r, 3),
                "net_pnl": round(res.net_pnl, 2),
                "max_dd_pct": round(res.max_drawdown_pct, 2),
                "final_equity": round(res.final_equity, 2),
                "params": str(g),
            }
            all_rows.append(row)
            if res.win_rate >= 99.999 and res.total_trades >= 5:
                hit_100.append(row)
            if best_any is None or res.net_pnl > best_any["net_pnl"]:
                best_any = dict(row)

        # Top WR and top PnL for this symbol
        sym_rows = [r for r in all_rows if r["symbol"] == symbol and r["trades"] >= 5]
        if sym_rows:
            top_wr = max(sym_rows, key=lambda r: (r["win_rate"], r["net_pnl"]))
            top_pnl = max(sym_rows, key=lambda r: r["net_pnl"])
            print(f"  TOP WR (≥5 trades): {top_wr['win_rate']}% PnL={top_wr['net_pnl']} tag={top_wr['tag']}", flush=True)
            print(f"  TOP PnL: {top_pnl['net_pnl']} WR={top_pnl['win_rate']}% tag={top_pnl['tag']}", flush=True)
            print(f"  Hits with WR≈100% and ≥5 trades: {len(hit_100)}", flush=True)

    table = pd.DataFrame(all_rows)
    out_csv = ROOT / "reports" / "book_optimal_search.csv"
    table.to_csv(out_csv, index=False)

    # Best configs summary
    usable = table[table["trades"] >= 5].copy()
    lines = [
        "# Book-optimal algorithm — measured search (NOT a promise)",
        "",
        "Synthesized from all library books: session gates (Silvani/Fabris), HTF trend",
        "(Ponsi/Damir/DraKoln), NTZ/ORB/squeeze/pullback triggers, VWAP side (Aziz),",
        "min R:R (Damir/Afshari/Thomas), cost filter (Silvani/Harris), 1% risk.",
        "",
        f"TF: `{timeframe}` · Start equity: `$10,000` · Costs included · No look-ahead",
        "",
        "## Did we find 100% win rate?",
    ]
    perfect = usable[usable["win_rate"] >= 99.999]
    if perfect.empty:
        lines.append(
            "**No.** Across all baselines + parameter grid, **zero** configs hit "
            "**100% WR with ≥5 trades**."
        )
    else:
        lines.append("**Yes (tiny/suspicious)** — inspect:")
        for _, r in perfect.iterrows():
            lines.append(
                f"- `{r['symbol']}` {r['tag']} WR={r['win_rate']} trades={r['trades']} PnL={r['net_pnl']}"
            )

    lines += ["", "## Best by net PnL (trades ≥ 5)", ""]
    if not usable.empty:
        top = usable.sort_values("net_pnl", ascending=False).head(10)
        lines += [
            "| Symbol | Tag | Trades | WR% | PF | Exp R | Net PnL | MaxDD% |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for _, r in top.iterrows():
            pf = "inf" if pd.isna(r["profit_factor"]) else f"{r['profit_factor']:.3f}"
            lines.append(
                f"| `{r['symbol']}` | `{r['tag']}` | {r['trades']} | {r['win_rate']:.1f} | {pf} | "
                f"{r['expectancy_r']:.3f} | {r['net_pnl']:.2f} | {r['max_dd_pct']:.2f} |"
            )

    lines += ["", "## Best by win rate (trades ≥ 5)", ""]
    if not usable.empty:
        topw = usable.sort_values(["win_rate", "net_pnl"], ascending=False).head(10)
        lines += [
            "| Symbol | Tag | Trades | WR% | Net PnL | Exp R |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for _, r in topw.iterrows():
            lines.append(
                f"| `{r['symbol']}` | `{r['tag']}` | {r['trades']} | {r['win_rate']:.1f} | "
                f"{r['net_pnl']:.2f} | {r['expectancy_r']:.3f} |"
            )

    lines += [
        "",
        "## Verdict",
        "- Books (Ponsi, DraKoln, Windsor, Afshari’s own Ch.6, Elder/Tharp) reject guaranteed 100%.",
        "- This search **tried** the confluence engine + tight R:R high-WR attempts.",
        "- Use the **best PnL** config if positive; never size as if WR=100%.",
        "",
        f"CSV: `{out_csv}`",
        "",
        "Run: `python scripts/run_backtest.py --config config_book_optimal.yaml`",
    ]
    md = ROOT / "reports" / "BOOK_OPTIMAL.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines), flush=True)
    print(f"\nWrote {md}", flush=True)


if __name__ == "__main__":
    main()
