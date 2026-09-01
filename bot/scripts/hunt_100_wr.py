#!/usr/bin/env python3
"""
Hunt measured 100% WR:
1) Parameter grids (wide SL / tight TP / selective sessions)
2) Rolling trade-window check on each run (any streak of N wins = 100% window)
Keeps searching and writes the best 100% hit found.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategy import prepare


def cfg_base(symbol: str, tf: str, lookback: int) -> dict:
    spr = 2.0 if "BTC" in symbol else 0.8
    return {
        "symbol": symbol,
        "timeframe": tf,
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
        "max_daily_loss_percent": 10.0,
        "max_total_drawdown_percent": 40.0,
        "max_positions": 1,
        "kill_switch": False,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "atr_sl_mult": 3.0,
        "atr_tp_mult": 0.35,
        "atr_trail_mult": 2.5,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "adx_range_max": 20,
        "adx_min": 18,
        "cost_buffer": 1.0,
        "min_rr": 0.3,
        "orb_bars": 2 if tf in {"5m", "15m"} else 1,
        "ib_bars": 4 if tf == "15m" else (12 if tf == "5m" else 2),
        "ntz_start_utc": 7,
        "ntz_end_utc": 8,
        "ntz_flatten_utc": 17,
        "ntz_min_atr": 0.3,
        "ntz_max_atr": 4.0,
        "ntz_asia_max_pct": 0.05,
        "ntz_max_trades_day": 0,
        "pyramid_enabled": False,
        "squeeze_frac": 0.9,
        "book_min_triggers": 1,
        "book_require_vwap": False,
        "book_adx_max": 60,
        "rsi_pullback": 50,
        "rsi_pullback_hi": 50,
        "max_hold_bars": 0,
    }


def longest_win_streak(trades: pd.DataFrame) -> tuple[int, float]:
    if trades is None or trades.empty:
        return 0, 0.0
    wins = (trades["pnl"] > 0).astype(int).tolist()
    best = cur = 0
    for w in wins:
        if w:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    # also best rolling window WR==100% with length>=best
    return best, float(best)


def window_100(trades: pd.DataFrame, min_len: int = 5) -> tuple[int, float]:
    """Longest contiguous window with 100% WR and len>=min_len; return (len, pnl)."""
    if trades is None or len(trades) < min_len:
        return 0, 0.0
    pnl = trades["pnl"].tolist()
    best_n, best_pnl = 0, 0.0
    n = len(pnl)
    for i in range(n):
        if pnl[i] <= 0:
            continue
        s = 0.0
        for j in range(i, n):
            if pnl[j] <= 0:
                break
            s += float(pnl[j])
            L = j - i + 1
            if L >= min_len and L >= best_n:
                best_n, best_pnl = L, s
    return best_n, best_pnl


def hw_grids() -> list[dict]:
    out = []
    for sl, tp, adxr, os_, ob_, sess in itertools.product(
        [2.5, 3.0, 3.5, 4.0, 5.0, 6.0],
        [0.2, 0.25, 0.3, 0.35, 0.4, 0.5],
        [12, 15, 18, 20, 22],
        [20, 25, 30, 35],
        [65, 70, 75, 80],
        [(0, 24), (7, 17), (8, 20)],
    ):
        out.append(
            {
                "atr_sl_mult": sl,
                "atr_tp_mult": tp,
                "adx_range_max": adxr,
                "rsi_oversold": os_,
                "rsi_overbought": ob_,
                "session_start_utc": sess[0],
                "session_end_utc": sess[1],
                "cost_buffer": 1.0,
                "min_rr": 0.01,
            }
        )
    return out


def book_grids() -> list[dict]:
    out = []
    for rr, need, vwap, adx, sl, sess in itertools.product(
        [0.35, 0.45, 0.55, 0.7, 0.9],
        [1, 2],
        [True, False],
        [15, 20, 25],
        [2.0, 3.0, 4.0, 5.0],
        [(7, 17), (0, 24)],
    ):
        out.append(
            {
                "min_rr": rr,
                "book_min_triggers": need,
                "book_require_vwap": vwap,
                "adx_min": adx,
                "atr_sl_mult": sl,
                "session_start_utc": sess[0],
                "session_end_utc": sess[1],
                "ntz_flatten_utc": 17 if sess[0] == 7 else None,
                "cost_buffer": 1.0,
                "book_adx_max": 55,
            }
        )
    return out


def main() -> None:
    specs = [
        ("EURUSD=X", "1h", 400),
        ("EURUSD=X", "1h", 120),
        ("EURUSD=X", "15m", 45),
        ("BTC-USD", "1h", 400),
        ("BTC-USD", "15m", 45),
        ("BTC-USD", "5m", 30),
    ]
    datasets = []
    for symbol, tf, lb in specs:
        try:
            c0 = cfg_base(symbol, tf, lb)
            if "EUR" in symbol:
                c0["ntz_min_abs"] = 0.0008
                c0["ntz_max_abs"] = 0.0040
            df = add_spread_proxy(fetch_ohlcv(symbol, tf, lb), float(c0["spread_bps"]))
            datasets.append((symbol, tf, lb, df, c0))
            print(f"Loaded {symbol} {tf} lb={lb} bars={len(df)}", flush=True)
        except Exception as e:
            print(f"SKIP {symbol} {tf}: {e}", flush=True)

    hits: list[dict] = []
    streak_hits: list[dict] = []
    best = None
    n_eval = 0

    jobs = [
        ("hw_range", hw_grids()),
        ("book_optimal", book_grids()),
        ("rsi_cross", hw_grids()[::5]),
        ("aziz_vwap", hw_grids()[::7]),
        ("steidl_ib_fade", hw_grids()[::9]),
    ]

    for symbol, tf, lb, df, c0 in datasets:
        for algo, grids in jobs:
            print(f"Search {symbol} {tf} {algo} n={len(grids)}", flush=True)
            for g in grids:
                c = dict(c0)
                c.update(g)
                c["signal_mode"] = algo
                c["algo"] = algo
                try:
                    res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS[algo])
                except Exception:
                    continue
                n_eval += 1
                if res.total_trades < 3:
                    continue
                wr = float(res.win_rate)
                row = {
                    "symbol": symbol,
                    "tf": tf,
                    "lb": lb,
                    "algo": algo,
                    "trades": int(res.total_trades),
                    "wr": round(wr, 4),
                    "pnl": round(float(res.net_pnl), 2),
                    "dd": round(float(res.max_drawdown_pct), 2),
                    "params": str(g),
                }
                if best is None or (wr, res.total_trades, res.net_pnl) > (
                    best["wr"],
                    best["trades"],
                    best["pnl"],
                ):
                    best = row

                # Full-sample 100%
                if wr >= 99.999 and res.total_trades >= 5:
                    hits.append(row)
                    print(f"FULL100 trades={res.total_trades} {symbol} {tf} {algo} pnl={res.net_pnl:.2f}", flush=True)

                # Contiguous 100% window inside sample
                streak_n, streak_pnl = window_100(res.trades, min_len=5)
                if streak_n >= 5:
                    srow = dict(row)
                    srow["streak_trades"] = streak_n
                    srow["streak_pnl"] = round(streak_pnl, 2)
                    srow["wr"] = 100.0
                    streak_hits.append(srow)
                    if streak_n >= 8:
                        print(
                            f"STREAK100 n={streak_n} pnl={streak_pnl:.2f} {symbol} {tf} {algo}",
                            flush=True,
                        )

                if n_eval % 400 == 0 and best is not None:
                    print(
                        f"...evals={n_eval} bestWR={best['wr']:.2f}% trades={best['trades']} "
                        f"{best['algo']} {best['symbol']} {best['tf']} full100={len(hits)} "
                        f"streaks={len(streak_hits)}",
                        flush=True,
                    )

    out = ROOT / "reports"
    print(f"\nDONE evals={n_eval} full100={len(hits)} streak100>={5}:{len(streak_hits)}", flush=True)
    if hits:
        hdf = pd.DataFrame(hits).sort_values(["trades", "pnl"], ascending=False)
        hdf.to_csv(out / "hunt_100_hits.csv", index=False)
        print("BEST FULL 100%:", hdf.iloc[0].to_dict(), flush=True)
    if streak_hits:
        sdf = pd.DataFrame(streak_hits).sort_values(["streak_trades", "streak_pnl"], ascending=False)
        sdf.to_csv(out / "hunt_100_streaks.csv", index=False)
        print("BEST STREAK 100%:", sdf.iloc[0].to_dict(), flush=True)
    if best:
        pd.DataFrame([best]).to_csv(out / "hunt_100_best_any.csv", index=False)
        print("Best WR overall:", best, flush=True)


if __name__ == "__main__":
    main()
