#!/usr/bin/env python3
"""
Maximize P(profit) for $100 / 2-hour sessions.

Book-driven constraints (Chan, Harris, Tharp, Elder, Davey/Aronson):
- Costs dominate high-frequency scalps → fewer trades, wider targets vs spread
- Risk small enough that one loss isn't fatal to the session math, but
  for P(session>0) the key is trade quality + max 1–2 trades / session
- Prefer mean-reversion only with filters, or selective breakouts
- Score primarily: fraction of 2h windows with PnL > 0
"""
from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.features import enrich_all
from aegis.risk import RiskEngine
from aegis.session_algos import ALGOS, SignalFn


def prepare_frame(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    frame = enrich_all(df, cfg)
    frame["ema_fast_prev"] = frame["ema_fast"].shift(1)
    frame["ema_slow_prev"] = frame["ema_slow"].shift(1)
    frame["rsi_prev"] = frame["rsi"].shift(1)
    frame["macd_prev"] = frame["macd"].shift(1)
    frame["macd_signal_prev"] = frame["macd_signal"].shift(1)
    frame["close_prev"] = frame["close"].shift(1)
    return frame


def run_session(
    frame: pd.DataFrame,
    cfg: dict[str, Any],
    signal_fn: SignalFn,
    start_i: int,
    end_i: int,
) -> dict[str, Any]:
    risk = RiskEngine.from_config(cfg)
    equity = float(cfg.get("starting_equity", 100))
    start_eq = equity
    cost_bps = float(cfg.get("spread_bps", 1.0)) + float(cfg.get("slippage_bps", 0.5))
    max_hold = int(cfg.get("max_hold_bars", 0) or 0)
    max_trades = int(cfg.get("max_trades_per_session", 99) or 99)
    trades = 0
    wins = 0
    pos: Optional[dict[str, Any]] = None

    lo = max(0, start_i - 1)
    for i in range(lo, min(end_i, len(frame) - 1)):
        row = frame.iloc[i]
        nxt = frame.iloc[i + 1]
        in_win = start_i <= i < end_i
        risk.update(equity, now=pd.Timestamp(row["time"]).to_pydatetime())

        if pos is not None:
            side = pos["side"]
            high, low = float(nxt["high"]), float(nxt["low"])
            pos["bars_held"] = int(pos.get("bars_held", 0)) + 1
            exit_price = None
            sl, tp = pos["sl"], pos.get("tp")
            if side == "buy":
                if low <= sl:
                    exit_price = sl
                elif tp is not None and high >= tp:
                    exit_price = tp
            else:
                if high >= sl:
                    exit_price = sl
                elif tp is not None and low <= tp:
                    exit_price = tp
            if exit_price is None and max_hold > 0 and pos["bars_held"] >= max_hold:
                exit_price = float(nxt["close"])
            if exit_price is None and i + 1 >= end_i:
                exit_price = float(nxt["close"])
            if exit_price is not None:
                move = (exit_price - pos["entry"]) if side == "buy" else (pos["entry"] - exit_price)
                cost = pos["entry"] * (cost_bps / 10000.0) * 2
                pnl = pos["units"] * (move - cost)
                equity += pnl
                trades += 1
                if pnl > 0:
                    wins += 1
                pos = None
            continue

        if not in_win or trades >= max_trades:
            continue
        ok, _ = risk.allow(equity, 0)
        if not ok:
            continue
        sig = signal_fn(row, cfg)
        if sig is None:
            continue
        entry = float(nxt["open"])
        if sig.side == "buy":
            sl = entry - abs(sig.entry - sig.sl)
            tp = entry + abs(sig.tp - sig.entry) if sig.tp is not None else None
        else:
            sl = entry + abs(sig.sl - sig.entry)
            tp = entry - abs(sig.entry - sig.tp) if sig.tp is not None else None
        units = risk.size_units(
            equity, entry, sl, min_stop=abs(entry) * float(cfg.get("min_atr_pct", 0.0) or 0.0)
        )
        if units <= 0:
            continue
        pos = {"side": sig.side, "entry": entry, "sl": sl, "tp": tp, "units": units, "bars_held": 0}

    pnl = equity - start_eq
    return {"pnl": pnl, "equity": equity, "trades": trades, "wins": wins}


@dataclass
class Candidate:
    name: str
    algo: str
    timeframe: str
    params: dict[str, Any]
    p_profit: float
    mean_pnl: float
    median_pnl: float
    best: float
    worst: float
    active_frac: float
    avg_trades: float
    sessions: int
    active: int


def evaluate(
    frame: pd.DataFrame,
    cfg: dict[str, Any],
    algo: str,
    bars_2h: int,
    warmup: int,
    step: int,
) -> Candidate:
    signal_fn = ALGOS[algo]
    rows = []
    i = warmup
    while i + bars_2h < len(frame):
        rows.append(run_session(frame, cfg, signal_fn, i, i + bars_2h))
        i += step
    w = pd.DataFrame(rows)
    active = w[w["trades"] > 0]
    p_overall = float((w["pnl"] > 0).mean()) if len(w) else 0.0
    p_active = float((active["pnl"] > 0).mean()) if len(active) else 0.0
    coverage = len(active) / max(len(w), 1)
    # Primary: overall chance a random 2h play ends green (flats count as not profit)
    # Soft penalty if almost never trades (useless for "play 2 hours")
    p_score = p_overall if coverage >= 0.10 else p_overall * 0.5
    return Candidate(
        name=f"{algo}|{cfg.get('timeframe')}|r{cfg.get('risk_percent')}|mt{cfg.get('max_trades_per_session')}",
        algo=algo,
        timeframe=str(cfg.get("timeframe")),
        params={
            k: cfg[k]
            for k in (
                "risk_percent",
                "atr_sl_mult",
                "atr_tp_mult",
                "atr_trail_mult",
                "rsi_oversold",
                "rsi_overbought",
                "adx_range_max",
                "adx_min",
                "max_trades_per_session",
                "cost_buffer",
                "max_hold_bars",
                "spread_bps",
                "slippage_bps",
                "session_start_utc",
                "session_end_utc",
            )
            if k in cfg
        },
        p_profit=p_score,
        mean_pnl=float(w["pnl"].mean()) if len(w) else 0.0,
        median_pnl=float(w["pnl"].median()) if len(w) else 0.0,
        best=float(w["pnl"].max()) if len(w) else 0.0,
        worst=float(w["pnl"].min()) if len(w) else 0.0,
        active_frac=coverage,
        avg_trades=float(active["trades"].mean()) if len(active) else 0.0,
        sessions=len(w),
        active=len(active),
    )


def base_cfg(symbol: str, timeframe: str) -> dict[str, Any]:
    spread = 2.0 if "BTC" in symbol else 1.0
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "starting_equity": 100.0,
        "ema_fast": 20 if timeframe != "1h" else 50,
        "ema_slow": 50 if timeframe != "1h" else 200,
        "atr_period": 14,
        "bb_period": 20,
        "bb_std": 2.0,
        "rsi_period": 14,
        "adx_period": 14,
        "adx_trend_threshold": 25,
        "donchian_period": 20,
        "spread_bps": spread,
        "slippage_bps": spread * 0.5,
        "min_atr_pct": 0.0,
        "max_daily_loss_percent": 80.0,
        "max_total_drawdown_percent": 90.0,
        "max_positions": 1,
        "kill_switch": False,
        "session_start_utc": 7 if "EUR" in symbol else 0,
        "session_end_utc": 21 if "EUR" in symbol else 24,
        "cost_buffer": 2.0,
        "atr_trail_mult": 2.5,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="BTC-USD")
    args = parser.parse_args()

    # Cache data per timeframe
    data: dict[str, pd.DataFrame] = {}
    for tf, days in (("5m", 30), ("15m", 59), ("1h", 120)):
        raw = fetch_ohlcv(args.symbol, tf, days)
        data[tf] = add_spread_proxy(raw, 2.0 if "BTC" in args.symbol else 1.0)
        print(f"Loaded {args.symbol} {tf}: {len(data[tf])} bars")

    bars_map = {"5m": 24, "15m": 8, "1h": 2}
    step_map = {"5m": 12, "15m": 4, "1h": 1}

    results: list[Candidate] = []

    # Grid — focused, book-aligned (not insane combinatorial explosion)
    grid = []
    for algo in ALGOS:
        for tf in ("5m", "15m", "1h"):
            for risk in (5.0, 8.0, 12.0):
                for max_trades in (1, 2):
                    for sl, tp in ((2.0, 1.2), (2.5, 1.5), (1.8, 2.2), (2.0, 2.5)):
                        for cost_buffer in (1.5, 2.5):
                            grid.append(
                                {
                                    "algo": algo,
                                    "timeframe": tf,
                                    "risk_percent": risk,
                                    "max_trades_per_session": max_trades,
                                    "atr_sl_mult": sl,
                                    "atr_tp_mult": tp,
                                    "cost_buffer": cost_buffer,
                                    "rsi_oversold": 30 if algo != "trend_pullback" else 40,
                                    "rsi_overbought": 70 if algo != "trend_pullback" else 60,
                                    "adx_range_max": 22,
                                    "adx_min": 20 if algo == "trend_pullback" else 25,
                                    "max_hold_bars": bars_map[tf],
                                }
                            )

    # Deduplicate / subsample if huge: keep every combo but it's ~5*3*3*2*4*2 = 720 — OK
    print(f"Evaluating {len(grid)} configs...\n")
    frames: dict[str, pd.DataFrame] = {}

    for n, g in enumerate(grid, 1):
        tf = g["timeframe"]
        cfg = base_cfg(args.symbol, tf)
        cfg.update({k: v for k, v in g.items() if k != "algo"})
        if tf not in frames:
            frames[tf] = prepare_frame(data[tf], cfg)
        # refresh enrich if params affecting indicators change — use fixed enrich cfg
        cand = evaluate(
            frames[tf],
            cfg,
            g["algo"],
            bars_map[tf],
            warmup=300 if tf != "1h" else 250,
            step=step_map[tf],
        )
        results.append(cand)
        if n % 100 == 0:
            best = max(results, key=lambda c: (c.p_profit, c.mean_pnl))
            print(f"  [{n}/{len(grid)}] best so far P(profit)~{best.p_profit*100:.1f}% {best.name}")

    # Rank: P(profit) first, then mean pnl, then coverage
    results.sort(key=lambda c: (c.p_profit, c.mean_pnl, c.active_frac), reverse=True)
    top = results[:25]

    print("\n=== TOP 25 BY P(2h PROFIT) ===")
    rows = []
    for i, c in enumerate(top, 1):
        print(
            f"{i:2d}. {c.name:48s} P={c.p_profit*100:5.1f}%  "
            f"mean=${c.mean_pnl:7.2f} med=${c.median_pnl:7.2f}  "
            f"best=${c.best:6.2f} worst=${c.worst:7.2f}  "
            f"active={c.active_frac*100:4.1f}% avgN={c.avg_trades:.2f}"
        )
        rows.append(
            {
                "rank": i,
                "name": c.name,
                "algo": c.algo,
                "timeframe": c.timeframe,
                "p_profit": round(c.p_profit * 100, 2),
                "mean_pnl": round(c.mean_pnl, 2),
                "median_pnl": round(c.median_pnl, 2),
                "best": round(c.best, 2),
                "worst": round(c.worst, 2),
                "active_frac": round(c.active_frac * 100, 2),
                "avg_trades": round(c.avg_trades, 2),
                **{f"p_{k}": v for k, v in c.params.items()},
            }
        )

    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(out_dir / "optimize_2h_profit_prob.csv", index=False)

    winner = results[0]
    # Write winning config
    win_cfg = base_cfg(args.symbol, winner.timeframe)
    win_cfg.update(winner.params)
    win_cfg["signal_mode"] = winner.algo
    win_cfg["lookback_days"] = 30 if winner.timeframe == "5m" else (59 if winner.timeframe == "15m" else 120)
    win_cfg["mode"] = "paper"
    win_cfg["poll_seconds"] = 30
    # map algo into strategy signal_mode names used by paper bot — store explicit
    win_cfg["algo"] = winner.algo
    cfg_path = ROOT / "config_100_2h.yaml"
    with cfg_path.open("w", encoding="utf-8") as f:
        f.write("# Auto-optimized for max P(profit) on $100 / 2h sessions\n")
        f.write(f"# Winner: {winner.name} | P(profit)~{winner.p_profit*100:.1f}% | mean=${winner.mean_pnl:.2f}\n")
        yaml.safe_dump(win_cfg, f, sort_keys=False)

    md = out_dir / "OPTIMIZE_2H.md"
    md.write_text(
        "\n".join(
            [
                "# 2-hour profit-probability optimization",
                "",
                f"Symbol: `{args.symbol}`",
                "",
                "## Book principles applied",
                "- **Chan**: transaction costs kill high-frequency mean reversion → fewer trades, cost gate",
                "- **Harris**: spread/slippage modeled; skip trades that cannot clear costs",
                "- **Tharp/Elder**: fixed fractional risk; hard loss caps",
                "- **Grimes/Clenow**: trend pullback & ADX-filtered breakout alternatives",
                "- **Davey/Aronson**: compare many specs on same metric (P(session>0))",
                "",
                f"## Winner: `{winner.name}`",
                f"- **P(profit | active 2h):** **{winner.p_profit*100:.1f}%**",
                f"- Mean active PnL: `${winner.mean_pnl:.2f}`",
                f"- Median: `${winner.median_pnl:.2f}`",
                f"- Best / Worst: `${winner.best:.2f}` / `${winner.worst:.2f}`",
                f"- Session coverage: `{winner.active_frac*100:.1f}%` of windows traded",
                f"- Avg trades/active session: `{winner.avg_trades:.2f}`",
                "",
                f"Written to `{cfg_path.name}`.",
                f"Full table: `optimize_2h_profit_prob.csv`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nWinner P(profit)≈{winner.p_profit*100:.1f}% → {cfg_path}")
    print(f"Report: {md}")


if __name__ == "__main__":
    main()
