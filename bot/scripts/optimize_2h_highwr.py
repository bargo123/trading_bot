#!/usr/bin/env python3
"""Focused high win-rate search for max P($100 / 2h session profit)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

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
    frame["rsi_prev"] = frame["rsi"].shift(1)
    frame["close_prev"] = frame["close"].shift(1)
    return frame


def base_cfg(symbol: str, timeframe: str) -> dict[str, Any]:
    spread = 2.0 if "BTC" in symbol else 1.0
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "starting_equity": 100.0,
        "ema_fast": 20,
        "ema_slow": 50,
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
        "session_start_utc": 0,
        "session_end_utc": 24,
        "cost_buffer": 1.25,
        "atr_trail_mult": 2.5,
    }


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
    max_trades = int(cfg.get("max_trades_per_session", 1) or 1)
    trades = 0
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
                equity += pos["units"] * (move - cost)
                trades += 1
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
        units = risk.size_units(equity, entry, sl, min_stop=0.0)
        if units <= 0:
            continue
        pos = {"side": sig.side, "entry": entry, "sl": sl, "tp": tp, "units": units, "bars_held": 0}
    return {"pnl": equity - start_eq, "trades": trades}


def main() -> None:
    symbol = "BTC-USD"
    data = {
        "5m": add_spread_proxy(fetch_ohlcv(symbol, "5m", 30), 2.0),
        "15m": add_spread_proxy(fetch_ohlcv(symbol, "15m", 59), 2.0),
    }
    for tf, df in data.items():
        print(f"loaded {tf}: {len(df)}")

    bars = {"5m": 24, "15m": 8}
    step = {"5m": 12, "15m": 4}
    grid = []
    for algo in ("hw_range", "rsi_cross"):
        for tf in ("5m", "15m"):
            for risk in (3.0, 5.0, 8.0):
                for sl, tp in ((3.0, 0.6), (3.5, 0.7), (4.0, 0.8), (2.5, 0.5), (3.0, 1.0), (5.0, 0.8)):
                    for cb in (1.0, 1.25):
                        for adx_max in (22, 28, 40, 99):
                            for os, ob in ((25, 75), (30, 70), (35, 65)):
                                grid.append(
                                    {
                                        "algo": algo,
                                        "timeframe": tf,
                                        "risk_percent": risk,
                                        "max_trades_per_session": 1,
                                        "atr_sl_mult": sl,
                                        "atr_tp_mult": tp,
                                        "cost_buffer": cb,
                                        "adx_range_max": adx_max,
                                        "rsi_oversold": os,
                                        "rsi_overbought": ob,
                                        "adx_min": 18,
                                        "max_hold_bars": bars[tf],
                                        "atr_trail_mult": 2.5,
                                    }
                                )
    # Also asymmetric pullback (win less often but try)
    for tf in ("5m", "15m"):
        for risk in (5.0, 8.0):
            for sl, tp in ((1.5, 2.5), (2.0, 3.0), (1.2, 2.0)):
                grid.append(
                    {
                        "algo": "trend_pullback",
                        "timeframe": tf,
                        "risk_percent": risk,
                        "max_trades_per_session": 1,
                        "atr_sl_mult": sl,
                        "atr_tp_mult": tp,
                        "cost_buffer": 1.25,
                        "adx_range_max": 22,
                        "rsi_oversold": 40,
                        "rsi_overbought": 60,
                        "adx_min": 18,
                        "max_hold_bars": bars[tf],
                        "atr_trail_mult": 2.5,
                    }
                )

    print(f"Evaluating {len(grid)} configs")
    # Speed: evaluate every other config for RSI extremes duplicates, keep all pullbacks
    grid = [g for i, g in enumerate(grid) if g["algo"] == "trend_pullback" or i % 2 == 0]
    print(f"After subsample: {len(grid)}")
    frames: dict[str, pd.DataFrame] = {}
    results = []
    for n, g in enumerate(grid, 1):
        tf = g["timeframe"]
        cfg = base_cfg(symbol, tf)
        cfg.update({k: v for k, v in g.items() if k != "algo"})
        if tf not in frames:
            frames[tf] = prepare_frame(data[tf], cfg)
        rows = []
        i = 300
        fr = frames[tf]
        while i + bars[tf] < len(fr):
            rows.append(run_session(fr, cfg, ALGOS[g["algo"]], i, i + bars[tf]))
            i += step[tf]
        w = pd.DataFrame(rows)
        a = w[w["trades"] > 0]
        p_all = float((w["pnl"] > 0).mean()) if len(w) else 0.0
        p_act = float((a["pnl"] > 0).mean()) if len(a) else 0.0
        cov = len(a) / max(len(w), 1)
        results.append(
            {
                **g,
                "p_all": p_all,
                "p_act": p_act,
                "cov": cov,
                "mean": float(w["pnl"].mean()) if len(w) else 0.0,
                "mean_a": float(a["pnl"].mean()) if len(a) else 0.0,
                "best": float(w["pnl"].max()) if len(w) else 0.0,
                "worst": float(w["pnl"].min()) if len(w) else 0.0,
            }
        )
        if n % 100 == 0:
            best = max(results, key=lambda r: (r["p_act"] if r["cov"] >= 0.2 else 0, r["p_all"]))
            print(
                f"[{n}/{len(grid)}] best_act={best['p_act']*100:.1f}% "
                f"p_all={best['p_all']*100:.1f}% cov={best['cov']*100:.0f}% "
                f"{best['algo']} {best['timeframe']} SL{best['atr_sl_mult']}/TP{best['atr_tp_mult']}"
            )

    # Rank A: overall P(profit)
    by_all = sorted(results, key=lambda r: (r["p_all"], r["mean"]), reverse=True)
    # Rank B: conditional WR with enough coverage
    by_act = sorted(
        [r for r in results if r["cov"] >= 0.20],
        key=lambda r: (r["p_act"], r["p_all"], r["mean_a"]),
        reverse=True,
    )

    print("\n=== TOP 12 overall P(2h profit) ===")
    for i, r in enumerate(by_all[:12], 1):
        print(
            f"{i:2d}. {r['algo']:12s} {r['timeframe']} r{r['risk_percent']} "
            f"SL{r['atr_sl_mult']}/TP{r['atr_tp_mult']} adxMax{r['adx_range_max']} "
            f"P_all={r['p_all']*100:5.1f}% P_act={r['p_act']*100:5.1f}% cov={r['cov']*100:4.1f}% mean=${r['mean']:.2f}"
        )

    print("\n=== TOP 12 P(profit|trade) cov>=20% ===")
    for i, r in enumerate(by_act[:12], 1):
        print(
            f"{i:2d}. {r['algo']:12s} {r['timeframe']} r{r['risk_percent']} "
            f"SL{r['atr_sl_mult']}/TP{r['atr_tp_mult']} RSI{r['rsi_oversold']}/{r['rsi_overbought']} "
            f"P_act={r['p_act']*100:5.1f}% P_all={r['p_all']*100:5.1f}% cov={r['cov']*100:4.1f}% mean_a=${r['mean_a']:.2f}"
        )

    # Install the highest conditional WR with cov>=20% (what user asked: chance of profit)
    winner = by_act[0] if by_act else by_all[0]
    cfg = base_cfg(symbol, winner["timeframe"])
    for k in (
        "risk_percent",
        "atr_sl_mult",
        "atr_tp_mult",
        "cost_buffer",
        "adx_range_max",
        "rsi_oversold",
        "rsi_overbought",
        "adx_min",
        "max_trades_per_session",
        "max_hold_bars",
        "atr_trail_mult",
    ):
        cfg[k] = winner[k]
    cfg["signal_mode"] = winner["algo"]
    cfg["algo"] = winner["algo"]
    cfg["lookback_days"] = 30 if winner["timeframe"] == "5m" else 59
    cfg["mode"] = "paper"
    cfg["poll_seconds"] = 30

    out = ROOT / "config_100_2h.yaml"
    with out.open("w", encoding="utf-8") as f:
        f.write(
            f"# Max P(2h profit) search\n"
            f"# P(profit|trade)={winner['p_act']*100:.1f}% | overall={winner['p_all']*100:.1f}% | coverage={winner['cov']*100:.1f}%\n"
        )
        yaml.safe_dump(cfg, f, sort_keys=False)

    pd.DataFrame(by_act[:40]).to_csv(ROOT / "reports" / "optimize_2h_highwr.csv", index=False)
    (ROOT / "reports" / "OPTIMIZE_2H.md").write_text(
        "\n".join(
            [
                "# 2-hour profit-probability optimization (high-WR pass)",
                "",
                "Books: Chan (costs), Harris (spread), Tharp (R-multiples / asymmetric), Elder (risk), Grimes (pullbacks), Clenow (breakouts), Davey (test many).",
                "",
                f"## Installed winner: `{winner['algo']}` @ `{winner['timeframe']}`",
                f"- **P(profit | traded 2h): {winner['p_act']*100:.1f}%**",
                f"- Overall P(profit including flat sessions): {winner['p_all']*100:.1f}%",
                f"- Coverage (sessions with a trade): {winner['cov']*100:.1f}%",
                f"- Mean PnL (active): ${winner['mean_a']:.2f}",
                f"- Best / Worst: ${winner['best']:.2f} / ${winner['worst']:.2f}",
                f"- Params: risk={winner['risk_percent']}% SL={winner['atr_sl_mult']}ATR TP={winner['atr_tp_mult']}ATR RSI={winner['rsi_oversold']}/{winner['rsi_overbought']} max_trades=1",
                "",
                "Note: pushing session win-rate often means small targets + wide stops (high WR, modest expectancy). That is intentional for this objective.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nInstalled winner P_act={winner['p_act']*100:.1f}% → {out}")


if __name__ == "__main__":
    main()
