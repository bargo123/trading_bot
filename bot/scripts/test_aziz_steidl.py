#!/usr/bin/env python3
"""Test Aziz + Steidlmayer strategies vs baseline on same data."""
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
    # 5m → IB 12 bars (1h), ORB 3 bars (15m)
    # 15m → IB 4 bars (1h), ORB 2 bars (30m)
    if timeframe == "5m":
        orb_bars, ib_bars, lookback = 3, 12, 30
    elif timeframe == "15m":
        orb_bars, ib_bars, lookback = 2, 4, 45
    else:
        orb_bars, ib_bars, lookback = 1, 2, 120
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
        "session_start_utc": 0,
        "session_end_utc": 24,
        "atr_sl_mult": 1.5,
        "atr_tp_mult": 2.5,
        "atr_trail_mult": 2.5,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "adx_range_max": 25,
        "adx_min": 20,
        "cost_buffer": 1.5,
        "min_rr": 2.0,
        "orb_bars": orb_bars,
        "ib_bars": ib_bars,
        "orb_max_atr": 2.5,
        "ib_max_atr": 3.0,
        "fade_ib_max_atr": 1.2,
        "allow_responsive_ib": False,
        "max_hold_bars": 0,
    }


def main() -> None:
    symbol = "BTC-USD"
    timeframe = "15m"
    cfg = base_cfg(symbol, timeframe)
    print(f"Fetching {symbol} {timeframe}…", flush=True)
    df = add_spread_proxy(fetch_ohlcv(symbol, timeframe, int(cfg["lookback_days"])), float(cfg["spread_bps"]))
    print(f"Bars: {len(df)} | {df['time'].iloc[0]} → {df['time'].iloc[-1]}", flush=True)

    # Smoke: features
    frame = enrich_all(df, cfg)
    need = ["vwap", "orb_high", "ib_high", "orb_break_up", "ib_break_up", "vwap_reclaim"]
    missing = [c for c in need if c not in frame.columns]
    if missing:
        raise SystemExit(f"Missing features: {missing}")
    print(
        f"Feature smoke OK | VWAP last={frame['vwap'].iloc[-1]:.2f} "
        f"ORB breaks={(frame['orb_break_up']|frame['orb_break_dn']).sum()} "
        f"IB breaks={(frame['ib_break_up']|frame['ib_break_dn']).sum()}",
        flush=True,
    )

    algos = [
        "aziz_orb",
        "aziz_vwap",
        "steidl_ib_break",
        "steidl_ib_fade",
        "breakout_adx",
        "hw_range",
    ]
    rows = []
    for name in algos:
        c = dict(cfg)
        c["signal_mode"] = name
        c["algo"] = name
        res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS[name])
        print(f"\n=== {name} ===", flush=True)
        print(format_report(res), flush=True)
        rows.append(
            {
                "algo": name,
                "trades": res.total_trades,
                "win_rate": round(res.win_rate, 2),
                "profit_factor": None if res.profit_factor == float("inf") else round(res.profit_factor, 3),
                "max_dd_pct": round(res.max_drawdown_pct, 2),
                "expectancy_r": round(res.expectancy_r, 3),
                "net_pnl": round(res.net_pnl, 2),
                "final_equity": round(res.final_equity, 2),
            }
        )

    table = pd.DataFrame(rows).sort_values(["net_pnl", "win_rate"], ascending=False)
    out = ROOT / "reports" / "aziz_steidl_test.csv"
    table.to_csv(out, index=False)
    md = ROOT / "reports" / "AZIZ_STEIDL_TEST.md"
    lines = [
        f"# Aziz + Steidlmayer wiring test",
        "",
        f"Symbol: `{symbol}` · TF: `{timeframe}` · Bars: `{len(df)}` · Start equity: `$10,000`",
        "",
        "| Algo | Trades | WR% | PF | MaxDD% | Exp R | Net PnL | Final |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, r in table.iterrows():
        pf = "inf" if pd.isna(r["profit_factor"]) else f"{r['profit_factor']:.3f}"
        lines.append(
            f"| `{r['algo']}` | {r['trades']} | {r['win_rate']:.1f} | {pf} | "
            f"{r['max_dd_pct']:.2f} | {r['expectancy_r']:.3f} | {r['net_pnl']:.2f} | {r['final_equity']:.2f} |"
        )
    lines += [
        "",
        "## Wired from books",
        "- **Aziz ORB** — opening-range break, VWAP-related stop, min 2:1 R:R",
        "- **Aziz VWAP** — reclaim/reject VWAP, min 2:1 R:R",
        "- **Steidlmayer IB break** — go-with Initial Balance break (initiating filter)",
        "- **Steidlmayer IB fade** — fade first extension on narrow IB",
        "",
        f"CSV: `{out}`",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n=== RANKED ===", flush=True)
    print(table.to_string(index=False), flush=True)
    print(f"\nReport: {md}", flush=True)


if __name__ == "__main__":
    main()
