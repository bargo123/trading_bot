#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.config import load_config
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.strategies_catalog import STRATEGIES, prepare_bakeoff


def score_row(r: dict) -> float:
    """Composite score: prefer profitable systems, then WR, PF, low DD."""
    if r["trades"] < 10:
        return -1e9
    pf = r["profit_factor"] if r["profit_factor"] != float("inf") else 5.0
    # Profitability first; among profitable, blend WR and PF with DD penalty
    profit_bonus = 1000.0 if r["net_pnl"] > 0 else 0.0
    return profit_bonus + r["win_rate"] + 20.0 * pf - 2.0 * r["max_dd_pct"] + 5.0 * r["expectancy_r"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy bake-off across book-inspired systems")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--min-trades", type=int, default=10)
    args = parser.parse_args()

    cfg = load_config(args.config)
    # Fair shared risk/cost settings for bake-off
    cfg = {
        **cfg,
        "adx_trend_threshold": 25,
        "adx_range_max": 18,
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "atr_sl_mult": 2.5,
        "atr_tp_mult": 0.8,
        "session_start_utc": 7,
        "session_end_utc": 21,
        "spread_bps": float(cfg.get("spread_bps", 0.8)),
        "slippage_bps": float(cfg.get("slippage_bps", 0.4)),
        "risk_percent": float(cfg.get("risk_percent", 0.5)),
        "starting_equity": float(cfg.get("starting_equity", 10_000)),
        "min_atr_pct": float(cfg.get("min_atr_pct", 0.0004)),
    }

    df = fetch_ohlcv(cfg["symbol"], cfg["timeframe"], int(cfg.get("lookback_days", 700)))
    df = add_spread_proxy(df, float(cfg["spread_bps"]))
    print(f"Bake-off data: {len(df)} bars | {cfg['symbol']} {cfg['timeframe']}")
    print(f"Strategies: {len(STRATEGIES)}\n")

    rows: list[dict] = []
    for spec in STRATEGIES:
        res = run_backtest(df, cfg, prepare_fn=prepare_bakeoff, signal_fn=spec.signal_fn)
        pf = res.profit_factor
        row = {
            "id": spec.id,
            "name": spec.name,
            "book_basis": spec.book_basis,
            "trades": res.total_trades,
            "win_rate": round(res.win_rate, 2),
            "profit_factor": round(pf, 3) if pf != float("inf") else float("inf"),
            "max_dd_pct": round(res.max_drawdown_pct, 2),
            "expectancy_r": round(res.expectancy_r, 3),
            "net_pnl": round(res.net_pnl, 2),
            "final_equity": round(res.final_equity, 2),
        }
        row["score"] = round(score_row(row), 2)
        rows.append(row)
        print(
            f"  [{spec.id:16}] trades={row['trades']:4d}  WR={row['win_rate']:6.2f}%  "
            f"PF={row['profit_factor'] if row['profit_factor'] != float('inf') else 'inf':>6}  "
            f"DD={row['max_dd_pct']:5.2f}%  PnL={row['net_pnl']:8.2f}  score={row['score']}"
        )

    table = pd.DataFrame(rows).sort_values(
        ["score", "net_pnl", "win_rate"], ascending=[False, False, False]
    ).reset_index(drop=True)

    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "bakeoff_results.csv"
    md_path = out_dir / "BAKEOFF.md"
    table.to_csv(csv_path, index=False)

    eligible = table[table["trades"] >= args.min_trades]
    winner = eligible.iloc[0] if not eligible.empty else table.iloc[0]

    lines = [
        "# Strategy Bake-off",
        "",
        f"Symbol: `{cfg['symbol']}` · Timeframe: `{cfg['timeframe']}` · Bars: `{len(df)}`",
        "",
        "Same data, same risk engine, same costs. No look-ahead.",
        "",
        f"**Winner (composite score, ≥{args.min_trades} trades): `{winner['id']}` — {winner['name']}**",
        "",
        f"- Win rate: **{winner['win_rate']}%**",
        f"- Profit factor: **{winner['profit_factor']}**",
        f"- Max DD: **{winner['max_dd_pct']}%**",
        f"- Net PnL: **{winner['net_pnl']}**",
        f"- Trades: **{winner['trades']}**",
        f"- Book basis: {winner['book_basis']}",
        "",
        "## Ranked results",
        "",
        "| Rank | ID | Name | Trades | WR% | PF | MaxDD% | Exp R | Net PnL | Score |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, r in table.iterrows():
        pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.3f}"
        lines.append(
            f"| {i + 1} | `{r['id']}` | {r['name']} | {r['trades']} | {r['win_rate']:.2f} | "
            f"{pf} | {r['max_dd_pct']:.2f} | {r['expectancy_r']:.3f} | {r['net_pnl']:.2f} | {r['score']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- High win rate ≠ best system if PF/expectancy are weak.",
            "- Trend systems often have lower WR but larger winners.",
            "- Promote winner into live/paper only after you accept its trade-off profile.",
            "",
            f"CSV: `{csv_path}`",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n=== RANKING ===")
    print(
        table[
            ["id", "trades", "win_rate", "profit_factor", "max_dd_pct", "net_pnl", "score"]
        ].to_string(index=False)
    )
    print(f"\nWinner: {winner['id']} ({winner['name']})")
    print(f"Report: {md_path}")
    print(f"CSV:    {csv_path}")


if __name__ == "__main__":
    main()
