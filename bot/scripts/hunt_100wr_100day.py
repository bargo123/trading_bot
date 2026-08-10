#!/usr/bin/env python3
"""Hunt 100% WR configs that maximize $/day from $100 (book algos, corrected engine)."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest  # noqa: E402
from aegis.data import fetch_ohlcv  # noqa: E402

SYMBOLS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "GC=F", "XAUUSD=X"]
TFS = ["1h", "30m", "15m", "5m"]
ALGOS = ["hw_range", "rsi_cross", "chan_bb_scalp", "volman_scalp", "trend_pullback", "steidl_ib_fade", "book_optimal", "fabris_ntz"]
LOOKBACKS = [30, 45, 60, 75, 90]


def base_cfg(symbol: str, tf: str, days: int, algo: str) -> dict:
    return {
        "symbol": symbol,
        "timeframe": tf,
        "lookback_days": days,
        "starting_equity": 100.0,
        "signal_mode": algo,
        "algo": algo,
        "risk_percent": 100.0,
        "high_risk_mode": "traditional",
        "high_risk_safe": False,
        "allow_unsafe_high_risk": True,
        "hr_risk_max_cap": 100,
        "hr_equity_floor_frac": 0.01,
        "hr_max_consecutive_losses": 999,
        "max_daily_loss_percent": 100,
        "max_total_drawdown_percent": 100,
        "max_positions": 1,
        "pyramid_enabled": False,
        "kill_switch": False,
        "ema_fast": 20 if algo != "hw_range" else 50,
        "ema_slow": 200,
        "atr_period": 14,
        "adx_period": 14,
        "adx_trend_threshold": 99,
        "donchian_period": 55,
        "bb_period": 24,
        "bb_std": 1.8,
        "rsi_period": 14,
        "rsi_oversold": 40,
        "rsi_overbought": 65,
        "adx_range_max": 24,
        "atr_sl_mult": 3.0,
        "atr_tp_mult": 0.45,
        "atr_trail_mult": 3.0,
        "min_rr": 0.01,
        "min_atr_pct": 0.0002,
        "cost_buffer": 1.0,
        "spread_bps": 1.2 if "GC" in symbol or "XAU" in symbol else 0.8,
        "slippage_bps": 0.6 if "GC" in symbol or "XAU" in symbol else 0.4,
        "session_start_utc": 0,
        "session_end_utc": 21 if tf in {"1h", "30m"} else 24,
        "volman_require_dd": False,
        "volman_tp_pips": 5,
        "volman_sl_pips": 25,
        "volman_pip_size": 0.01 if "JPY" in symbol or "GC" in symbol or "XAU" in symbol else 0.0001,
        "ntz_start_utc": 7,
        "ntz_end_utc": 8,
        "ntz_flatten_utc": 17,
        "ntz_min_atr": 0.2,
        "ntz_max_atr": 5.0,
        "ntz_asia_max_pct": 0.1,
        "ntz_max_trades_day": 0,
        "orb_bars": 2,
        "ib_bars": 4,
        "book_min_triggers": 1,
        "mode": "paper",
        "test_name": "hunt_100day",
    }


def daily_stats(trades) -> tuple[float, float, int]:
    """Return (max_day_pnl, days_ge_100, n_days)."""
    if trades is None or len(trades) == 0:
        return 0.0, 0, 0
    t = trades.copy()
    t["day"] = t["exit_time"].astype("datetime64[ns, UTC]").dt.floor("D")
    by = t.groupby("day")["pnl"].sum()
    max_d = float(by.max()) if len(by) else 0.0
    ge = int((by >= 100).sum())
    return max_d, ge, int(len(by))


def score(res, span_days: float) -> dict:
    eq = float(res.final_equity)
    pnl = float(res.net_pnl)
    ppd = pnl / max(span_days, 0.01)
    max_day, days_ge100, ndays = daily_stats(res.trades)
    return {
        "n": res.total_trades,
        "wr": float(res.win_rate),
        "er": float(res.expectancy_r),
        "eq": eq,
        "pnl": pnl,
        "ppd": ppd,
        "max_day": max_day,
        "days_ge_100": days_ge100,
        "halt": res.halt_reason or "none",
        "span": span_days,
    }


def main() -> None:
    grid_sl = [2.0, 3.0, 4.5, 6.0]
    grid_tp = [0.25, 0.35, 0.45, 0.6]
    grid_os = [30, 40]
    grid_ob = [60, 70]
    grid_adx = [20, 28]
    # Prioritize known strong combo first
    seeds = [
        ("EURUSD=X", "1h", 90, "hw_range", 3.0, 0.45, 40, 65, 24),
        ("EURUSD=X", "1h", 60, "hw_range", 3.0, 0.45, 40, 65, 24),
        ("EURUSD=X", "1h", 75, "hw_range", 4.5, 0.3, 40, 65, 28),
        ("GBPUSD=X", "1h", 60, "hw_range", 3.0, 0.45, 40, 65, 24),
        ("GC=F", "1h", 60, "hw_range", 4.0, 0.35, 35, 65, 28),
        ("GC=F", "15m", 30, "hw_range", 5.0, 0.3, 30, 70, 30),
        ("EURUSD=X", "15m", 30, "volman_scalp", 3.0, 0.4, 40, 65, 24),
        ("EURUSD=X", "5m", 14, "chan_bb_scalp", 2.5, 0.5, 35, 65, 25),
    ]

    cache: dict[tuple, object] = {}
    hits: list[dict] = []
    best_any = None

    def get_raw(sym, tf, days):
        key = (sym, tf, days)
        if key not in cache:
            try:
                cache[key] = fetch_ohlcv(sym, tf, days)
            except Exception as e:
                print(f"FETCH FAIL {key}: {e}")
                cache[key] = None
        return cache[key]

    def try_one(sym, tf, days, algo, sl, tp, os_, ob, adx_r):
        nonlocal best_any
        raw = get_raw(sym, tf, days)
        if raw is None or len(raw) < 80:
            return
        cfg = base_cfg(sym, tf, days, algo)
        cfg.update(
            {
                "atr_sl_mult": sl,
                "atr_tp_mult": tp,
                "rsi_oversold": os_,
                "rsi_overbought": ob,
                "adx_range_max": adx_r,
                "bb_period": 24 if algo == "hw_range" else 20,
            }
        )
        try:
            res = run_backtest(raw, cfg)
        except Exception as e:
            print(f"BT FAIL {sym} {tf} {algo}: {e}")
            return
        if res.total_trades < 8:
            return
        t0 = raw["time"].iloc[0]
        t1 = raw["time"].iloc[-1]
        span = max((t1 - t0).total_seconds() / 86400.0, 0.01)
        s = score(res, span)
        row = {
            "symbol": sym,
            "tf": tf,
            "days": days,
            "algo": algo,
            "sl": sl,
            "tp": tp,
            "os": os_,
            "ob": ob,
            "adx": adx_r,
            **s,
        }
        if best_any is None or (s["wr"] == 100 and s["ppd"] > best_any.get("ppd", -1e9)) or (
            s["wr"] == 100 and best_any.get("wr", 0) < 100
        ):
            if s["wr"] == 100:
                best_any = row
        if s["wr"] >= 99.999 and s["n"] >= 8:
            hits.append(row)
            print(
                f"HIT 100% {sym:10} {tf:4} {algo:14} n={s['n']:3} "
                f"eq={s['eq']:.2f} $/d={s['ppd']:.2f} maxDay={s['max_day']:.2f} "
                f"days>=100={s['days_ge_100']} sl={sl} tp={tp}"
            )
        elif s["ppd"] >= 20 and s["wr"] >= 90:
            print(
                f"NEAR {sym:10} {tf:4} {algo:14} wr={s['wr']:.1f} n={s['n']:3} "
                f"eq={s['eq']:.2f} $/d={s['ppd']:.2f} maxDay={s['max_day']:.2f}"
            )

    print("=== SEEDS ===")
    for s in seeds:
        try_one(*s)

    # Priority: EURUSD 1h full → GC=F 1h/15m → GBP 1h → remaining TF → other algos
    phases = [
        ("=== GRID hw_range EURUSD 1h ===", [("EURUSD=X", "1h", d) for d in [45, 60, 90]]),
        ("=== GRID hw_range GC=F 1h/15m ===", [("GC=F", tf, d) for tf in ["1h", "15m"] for d in [45, 60, 90]]),
        ("=== GRID hw_range GBPUSD 1h ===", [("GBPUSD=X", "1h", d) for d in [45, 60, 90]]),
        ("=== GRID hw_range remaining TF ===", [
            (sym, tf, d)
            for sym in ["EURUSD=X", "GBPUSD=X", "GC=F"]
            for tf in ["30m", "15m"]
            for d in [45, 60, 90]
            if not (sym == "GC=F" and tf == "15m")
        ]),
    ]
    param_combos = list(itertools.product(grid_sl, grid_tp, grid_os, grid_ob, grid_adx))
    for label, combos in phases:
        print(label, f"({len(combos)} datasets x {len(param_combos)} params)")
        n_done = 0
        for sym, tf, days in combos:
            for sl, tp, os_, ob, adx_r in param_combos:
                try_one(sym, tf, days, "hw_range", sl, tp, os_, ob, adx_r)
                n_done += 1
            print(f"  done {sym} {tf} {days}d | hits={len(hits)} best_ppd={best_any['ppd'] if best_any else None}")

    print("=== OTHER ALGOS (coarser, EURUSD+GC only) ===")
    for sym, tf, days, algo in itertools.product(
        ["EURUSD=X", "GC=F"],
        ["1h", "15m"],
        [30, 60],
        ["rsi_cross", "chan_bb_scalp", "volman_scalp", "trend_pullback", "book_optimal"],
    ):
        for sl, tp in itertools.product([2.5, 4.0, 6.0], [0.25, 0.4, 0.55]):
            try_one(sym, tf, days, algo, sl, tp, 35, 65, 25)

    hits.sort(key=lambda r: (r["ppd"], r["max_day"], r["eq"]), reverse=True)
    out = {
        "n_hits": len(hits),
        "best_by_ppd": hits[0] if hits else best_any,
        "top10": hits[:10],
        "any_day_ge_100": [h for h in hits if h["days_ge_100"] > 0 or h["max_day"] >= 100][:20],
    }
    path = ROOT / "reports" / "HUNT_100WR_100DAY.md"
    path.write_text(
        "# Hunt: 100% WR maximizing $/day from $100\n\n"
        f"Hits: **{len(hits)}** with WR=100% and n>=8\n\n"
        "```json\n"
        + json.dumps(out, indent=2)
        + "\n```\n"
    )
    # Write best config yaml if we have a hit
    if hits:
        b = hits[0]
        cfg = base_cfg(b["symbol"], b["tf"], b["days"], b["algo"])
        cfg.update(
            {
                "atr_sl_mult": b["sl"],
                "atr_tp_mult": b["tp"],
                "rsi_oversold": b["os"],
                "rsi_overbought": b["ob"],
                "adx_range_max": b["adx"],
                "test_name": "hunt_best_100wr_ppd",
            }
        )
        ypath = ROOT / "config_hunt_best_100wr_100day.yaml"
        ypath.write_text(yaml.safe_dump(cfg, sort_keys=False))
        print(f"\nBEST ppd=${b['ppd']:.2f}/d eq={b['eq']:.2f} maxDay={b['max_day']:.2f} → {ypath}")
    print(f"Report → {path}")


if __name__ == "__main__":
    main()
