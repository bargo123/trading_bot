#!/usr/bin/env python3
"""Simulate $100 aggressive bot over independent 2-hour play sessions."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import format_report, run_backtest
from aegis.config import load_config
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.risk import RiskEngine
from aegis.strategy import prepare, signal_from_row


def run_session(
    frame: pd.DataFrame,
    cfg: dict[str, Any],
    start_i: int,
    end_i: int,
) -> dict[str, Any]:
    """Fresh $100 account; entries only allowed inside [start_i, end_i)."""
    risk = RiskEngine.from_config(cfg)
    equity = float(cfg.get("starting_equity", 100))
    start_eq = equity
    cost_bps = float(cfg.get("spread_bps", 1.0)) + float(cfg.get("slippage_bps", 0.5))
    max_hold = int(cfg.get("max_hold_bars", 0) or 0)
    trades: list[dict[str, Any]] = []
    pos: Optional[dict[str, Any]] = None

    # Need one bar before start for signal context; manage through end_i
    lo = max(0, start_i - 1)
    for i in range(lo, min(end_i, len(frame) - 1)):
        row = frame.iloc[i]
        nxt = frame.iloc[i + 1]
        in_session = start_i <= i < end_i
        risk.update(equity, now=pd.Timestamp(row["time"]).to_pydatetime())

        if pos is not None:
            side = pos["side"]
            high, low = float(nxt["high"]), float(nxt["low"])
            pos["bars_held"] = int(pos.get("bars_held", 0)) + 1
            exit_price = None
            outcome = None
            sl, tp = pos["sl"], pos.get("tp")
            if side == "buy":
                if low <= sl:
                    exit_price, outcome = sl, "sl"
                elif tp is not None and high >= tp:
                    exit_price, outcome = tp, "tp"
            else:
                if high >= sl:
                    exit_price, outcome = sl, "sl"
                elif tp is not None and low <= tp:
                    exit_price, outcome = tp, "tp"
            # Force flat at session end or max hold
            if exit_price is None and max_hold > 0 and pos["bars_held"] >= max_hold:
                exit_price, outcome = float(nxt["close"]), "time"
            if exit_price is None and i + 1 >= end_i:
                exit_price, outcome = float(nxt["close"]), "session_end"
            if exit_price is not None:
                move = (exit_price - pos["entry"]) if side == "buy" else (pos["entry"] - exit_price)
                cost = pos["entry"] * (cost_bps / 10000.0) * 2
                pnl = pos["units"] * (move - cost)
                equity += pnl
                trades.append(
                    {
                        "entry_time": pos["time"],
                        "exit_time": nxt["time"],
                        "side": side,
                        "pnl": pnl,
                        "outcome": outcome,
                    }
                )
                pos = None
            continue

        if not in_session:
            continue
        ok, _ = risk.allow(equity, 0)
        if not ok:
            continue
        sig = signal_from_row(row, cfg)
        if sig is None:
            continue
        entry = float(nxt["open"])
        if sig.side == "buy":
            sl_dist = abs(sig.entry - sig.sl)
            sl = entry - sl_dist
            tp = entry + abs(sig.tp - sig.entry) if sig.tp is not None else None
        else:
            sl_dist = abs(sig.sl - sig.entry)
            sl = entry + sl_dist
            tp = entry - abs(sig.entry - sig.tp) if sig.tp is not None else None
        units = risk.size_units(
            equity, entry, sl, min_stop=abs(entry) * float(cfg.get("min_atr_pct", 0.0) or 0.0)
        )
        if units <= 0:
            continue
        pos = {
            "side": sig.side,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "units": units,
            "time": nxt["time"],
            "bars_held": 0,
        }

    pnl = equity - start_eq
    tdf = pd.DataFrame(trades)
    wr = float((tdf["pnl"] > 0).mean() * 100) if not tdf.empty else 0.0
    return {
        "start": frame.iloc[start_i]["time"],
        "end": frame.iloc[min(end_i, len(frame) - 1)]["time"],
        "pnl": pnl,
        "equity": equity,
        "trades": len(trades),
        "win_rate": wr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="$100 / 2-hour aggressive simulation")
    parser.add_argument("--config", default=str(ROOT / "config_100_2h.yaml"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    start_eq = float(cfg.get("starting_equity", 100))
    df = fetch_ohlcv(cfg["symbol"], cfg["timeframe"], int(cfg.get("lookback_days", 30)))
    df = add_spread_proxy(df, float(cfg.get("spread_bps", 1.0)))
    frame = prepare(df, cfg)

    print(f"Config: {args.config}")
    print(
        f"Start: ${start_eq:.2f} | TF={cfg['timeframe']} | risk={cfg['risk_percent']}% | mode={cfg.get('signal_mode')}"
    )
    print(f"Data: {len(df)} bars | {df['time'].iloc[0]} -> {df['time'].iloc[-1]}\n")

    # Full-sample reference (same aggressive profile)
    res = run_backtest(df, cfg)
    print("=== FULL SAMPLE (one continuous account) ===")
    print(format_report(res))
    out = ROOT / "reports" / "sim_100_2h_trades.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not res.trades.empty:
        res.trades.to_csv(out, index=False)
        wins = res.trades.loc[res.trades["pnl"] > 0, "pnl"]
        losses = res.trades.loc[res.trades["pnl"] <= 0, "pnl"]
        print("\n=== ONE TRADE IMPACT ON $100 ===")
        if len(wins):
            print(f"Avg win:  ${wins.mean():.2f} -> ${start_eq + wins.mean():.2f}")
            print(f"Best win: ${wins.max():.2f} -> ${start_eq + wins.max():.2f}")
        if len(losses):
            print(f"Avg loss: ${losses.mean():.2f} -> ${start_eq + losses.mean():.2f}")
            print(f"Worst:    ${losses.min():.2f} -> ${start_eq + losses.min():.2f}")

    bars_2h = 24 if str(cfg.get("timeframe")) == "5m" else 2
    warmup = 300
    step = 12
    sessions = []
    i = warmup
    while i + bars_2h < len(frame):
        sessions.append(run_session(frame, cfg, i, i + bars_2h))
        i += step

    w = pd.DataFrame(sessions)
    active = w[w["trades"] > 0]
    print(f"\n=== FRESH $100 EVERY 2h SESSION ({len(w)} windows) ===")
    print(f"Sessions with trades: {len(active)} ({len(active)/max(len(w),1)*100:.1f}%)")
    print(f"Mean 2h PnL (all):      ${w['pnl'].mean():.2f} -> ${start_eq + w['pnl'].mean():.2f}")
    print(f"Median 2h PnL (all):    ${w['pnl'].median():.2f} -> ${start_eq + w['pnl'].median():.2f}")
    if not active.empty:
        print(f"Mean 2h PnL (active):   ${active['pnl'].mean():.2f} -> ${start_eq + active['pnl'].mean():.2f}")
        print(f"Median 2h PnL (active): ${active['pnl'].median():.2f} -> ${start_eq + active['pnl'].median():.2f}")
        print(f"Best 2h session:        ${active['pnl'].max():.2f} -> ${start_eq + active['pnl'].max():.2f}")
        print(f"Worst 2h session:       ${active['pnl'].min():.2f} -> ${start_eq + active['pnl'].min():.2f}")
        print(f"P(profit | traded):     {(active['pnl'] > 0).mean()*100:.1f}%")
        print(f"Avg trades / active 2h: {active['trades'].mean():.2f}")
        print(f"P90 2h PnL:             ${active['pnl'].quantile(0.9):.2f}")
        print(f"P10 2h PnL:             ${active['pnl'].quantile(0.1):.2f}")

    latest = run_session(frame, cfg, max(warmup, len(frame) - bars_2h - 1), len(frame) - 1)
    print("\n=== MOST RECENT 2 HOURS (fresh $100) ===")
    print(f"{latest['start']} -> {latest['end']}")
    print(
        f"Trades: {latest['trades']} | WR: {latest['win_rate']:.1f}% | "
        f"PnL: ${latest['pnl']:.2f} | End equity: ${latest['equity']:.2f}"
    )

    if not active.empty:
        print("\n=== TOP 5 BEST 2h ===")
        for _, r in active.sort_values("pnl", ascending=False).head(5).iterrows():
            print(f"  {r['start']}  n={int(r['trades'])}  PnL=${r['pnl']:.2f}  eq=${r['equity']:.2f}")
        print("\n=== TOP 5 WORST 2h ===")
        for _, r in active.sort_values("pnl", ascending=True).head(5).iterrows():
            print(f"  {r['start']}  n={int(r['trades'])}  PnL=${r['pnl']:.2f}  eq=${r['equity']:.2f}")

    report = ROOT / "reports" / "SIM_100_2H.md"
    best = float(active["pnl"].max()) if not active.empty else 0.0
    worst = float(active["pnl"].min()) if not active.empty else 0.0
    mean_a = float(active["pnl"].mean()) if not active.empty else 0.0
    report.write_text(
        "\n".join(
            [
                "# $100 / 2-hour aggressive play",
                "",
                f"- Config: `config_100_2h.yaml` (5m scalper_2h, {cfg['risk_percent']}% risk/trade)",
                f"- Continuous sample: `{res.total_trades}` trades, WR `{res.win_rate:.1f}%`, net `${res.net_pnl:.2f}`",
                f"- Independent 2h sessions: `{len(w)}` (with trades: `{len(active)}`)",
                f"- **Best 2h:** `${best:.2f}` → **${start_eq + best:.2f}**",
                f"- **Worst 2h:** `${worst:.2f}` → **${start_eq + worst:.2f}**",
                f"- **Avg active 2h:** `${mean_a:.2f}` → **${start_eq + mean_a:.2f}**",
                f"- **Latest 2h:** `${latest['pnl']:.2f}` → **${latest['equity']:.2f}**",
                "",
                "Live paper:",
                "```bash",
                "cd ~/trading-llm/bot && source .venv/bin/activate",
                "python scripts/run_paper.py --config config_100_2h.yaml",
                "```",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    w.to_csv(ROOT / "reports" / "sim_100_2h_sessions.csv", index=False)
    print(f"\nReport: {report}")


if __name__ == "__main__":
    main()
