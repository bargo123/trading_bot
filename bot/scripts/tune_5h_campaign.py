#!/usr/bin/env python3
"""
5-hour testing/tuning campaign.
Objective: maximize measured $ growth from $100 with high WR (prefer 100%),
using corrected backtest engine. Continuously writes live progress.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest  # noqa: E402
from aegis.data import fetch_ohlcv  # noqa: E402

DURATION_SEC = int(5 * 3600)  # 5 hours
REPORT = ROOT / "reports" / "TUNE_5H_LIVE.md"
BEST_YAML = ROOT / "config_tune_5h_best.yaml"
HITS_JSON = ROOT / "reports" / "tune_5h_hits.json"
PROGRESS_JSON = ROOT / "reports" / "tune_5h_progress.json"

SYMBOLS = ["GC=F", "EURUSD=X", "GBPUSD=X", "AUDUSD=X", "USDJPY=X", "NZDUSD=X"]
TFS = ["1h", "15m", "5m"]
ALGOS = [
    "hw_range",
    "rsi_cross",
    "trend_pullback",
    "chan_bb_scalp",
    "volman_scalp",
    "book_optimal",
    "steidl_ib_fade",
    "breakout_adx",
]
LOOKBACKS = [30, 45, 60, 75, 90]


@dataclass
class Hit:
    symbol: str
    tf: str
    days: int
    algo: str
    params: dict
    n: int
    wr: float
    er: float
    eq: float
    ppd: float
    max_day: float
    days_ge_100: int
    span: float
    halt: str
    score: float


def base_cfg(symbol: str, tf: str, days: int, algo: str) -> dict:
    gold = "GC" in symbol or "XAU" in symbol
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
        "ema_fast": 50 if algo == "hw_range" else 20,
        "ema_slow": 200,
        "atr_period": 14,
        "adx_period": 14,
        "adx_trend_threshold": 99,
        "donchian_period": 55,
        "bb_period": 24,
        "bb_std": 1.8,
        "rsi_period": 14,
        "rsi_oversold": 35,
        "rsi_overbought": 65,
        "adx_range_max": 25,
        "atr_sl_mult": 3.0,
        "atr_tp_mult": 0.45,
        "atr_trail_mult": 3.0,
        "min_rr": 0.01,
        "min_atr_pct": 0.0002,
        "cost_buffer": 1.0,
        "spread_bps": 1.2 if gold else 0.8,
        "slippage_bps": 0.6 if gold else 0.4,
        "session_start_utc": 0,
        "session_end_utc": 21 if tf == "1h" else 24,
        "volman_require_dd": False,
        "volman_tp_pips": 5,
        "volman_sl_pips": 20,
        "volman_pip_size": 0.01 if ("JPY" in symbol or gold) else 0.0001,
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
        "test_name": "tune_5h",
    }


def daily_stats(trades):
    if trades is None or len(trades) == 0:
        return 0.0, 0
    t = trades.copy()
    t["day"] = t["exit_time"].astype("datetime64[ns, UTC]").dt.floor("D")
    by = t.groupby("day")["pnl"].sum()
    return float(by.max()) if len(by) else 0.0, int((by >= 100).sum())


def neighbor_score(raw_full, cfg: dict, primary_days: int) -> float:
    """Average WR on longer/shorter windows sharing the same end (stability)."""
    wrs = []
    for d in sorted({primary_days - 15, primary_days, primary_days + 15, primary_days + 30}):
        if d < 20 or raw_full is None or len(raw_full) < 50:
            continue
        # use last d days of bars approximately by time
        end = raw_full["time"].iloc[-1]
        start = end - __import__("pandas").Timedelta(days=d)
        chunk = raw_full[raw_full["time"] >= start]
        if len(chunk) < 60:
            continue
        c = dict(cfg)
        c["lookback_days"] = d
        try:
            res = run_backtest(chunk, c)
        except Exception:
            continue
        if res.total_trades >= 5:
            wrs.append(float(res.win_rate))
    return sum(wrs) / len(wrs) if wrs else 0.0


def sample_params(rng: random.Random, phase: str) -> dict:
    if phase == "gold_focus":
        return {
            "atr_sl_mult": rng.choice([1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]),
            "atr_tp_mult": rng.choice([0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8]),
            "rsi_oversold": rng.choice([25, 30, 35, 40, 45]),
            "rsi_overbought": rng.choice([55, 60, 65, 70, 75]),
            "adx_range_max": rng.choice([18, 20, 22, 24, 26, 28, 30, 35]),
            "bb_period": rng.choice([18, 20, 22, 24, 28]),
            "bb_std": rng.choice([1.5, 1.8, 2.0, 2.2]),
            "cost_buffer": rng.choice([0.7, 0.85, 1.0, 1.15]),
            "session_end_utc": rng.choice([18, 20, 21, 22, 24]),
        }
    return {
        "atr_sl_mult": rng.uniform(1.2, 7.0),
        "atr_tp_mult": rng.uniform(0.15, 1.0),
        "rsi_oversold": rng.randint(20, 45),
        "rsi_overbought": rng.randint(55, 80),
        "adx_range_max": rng.randint(15, 40),
        "bb_period": rng.randint(16, 30),
        "bb_std": rng.choice([1.5, 1.8, 2.0, 2.2, 2.5]),
        "cost_buffer": rng.choice([0.6, 0.8, 1.0, 1.2]),
        "volman_tp_pips": rng.choice([3, 4, 5, 6, 8]),
        "volman_sl_pips": rng.choice([10, 15, 20, 25, 35]),
        "ema_fast": rng.choice([10, 20, 50]),
        "session_end_utc": rng.choice([17, 20, 21, 24]),
    }


def compute_score(wr: float, n: int, eq: float, ppd: float, neigh_wr: float) -> float:
    """Rank: prefer 100% WR, then $/day, equity, neighbor stability, sample size."""
    perfect = 1e6 if wr >= 99.999 else 0.0
    near = 1e4 * max(0.0, wr - 90.0)  # reward 90-99
    return perfect + near + 100.0 * ppd + eq + 5.0 * neigh_wr + 0.5 * n


def write_progress(state: dict, hits: list[Hit], best: Hit | None) -> None:
    PROGRESS_JSON.write_text(json.dumps(state, indent=2))
    top = sorted(hits, key=lambda h: h.score, reverse=True)[:25]
    lines = [
        "# 5-hour tune — live",
        "",
        f"- elapsed_h: {state['elapsed_sec']/3600:.2f} / 5.0",
        f"- trials: {state['trials']}",
        f"- fetch_errors: {state['fetch_errors']}",
        f"- bt_errors: {state['bt_errors']}",
        f"- hits_100wr: {state['hits_100']}",
        f"- phase: {state['phase']}",
        "",
        "## Best so far",
        "",
    ]
    if best:
        lines.append("```json")
        lines.append(json.dumps(asdict(best), indent=2, default=str))
        lines.append("```")
        lines.append("")
    lines.append("## Top hits")
    lines.append("")
    lines.append("| rank | symbol | tf | algo | n | wr | eq | $/d | maxDay | score |")
    lines.append("|---:|---|---|---|---:|---:|---:|---:|---:|---:|")
    for i, h in enumerate(top, 1):
        lines.append(
            f"| {i} | {h.symbol} | {h.tf} | {h.algo} | {h.n} | {h.wr:.1f} | "
            f"{h.eq:.2f} | {h.ppd:.2f} | {h.max_day:.2f} | {h.score:.1f} |"
        )
    lines.append("")
    REPORT.write_text("\n".join(lines))
    HITS_JSON.write_text(json.dumps([asdict(h) for h in top], indent=2, default=str))
    if best:
        cfg = base_cfg(best.symbol, best.tf, best.days, best.algo)
        cfg.update(best.params)
        cfg["test_name"] = "tune_5h_best"
        BEST_YAML.write_text(yaml.safe_dump(cfg, sort_keys=False))


def main() -> None:
    rng = random.Random(20260810)
    t0 = time.time()
    deadline = t0 + DURATION_SEC
    cache: dict[tuple, object] = {}
    hits: list[Hit] = []
    best: Hit | None = None
    seen: set[str] = set()
    state = {
        "trials": 0,
        "fetch_errors": 0,
        "bt_errors": 0,
        "hits_100": 0,
        "phase": "gold_focus",
        "elapsed_sec": 0.0,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    def get_raw(sym, tf, days):
        key = (sym, tf, days)
        if key not in cache:
            try:
                # fetch a bit extra for neighbor windows
                cache[key] = fetch_ohlcv(sym, tf, max(days + 40, days))
            except Exception as e:
                state["fetch_errors"] += 1
                print(f"FETCH_FAIL {key}: {e}", flush=True)
                cache[key] = None
        return cache[key]

    # Seed known best
    seeds = [
        ("GC=F", "1h", 45, "hw_range", {"atr_sl_mult": 2.0, "atr_tp_mult": 0.6, "rsi_oversold": 30, "rsi_overbought": 70, "adx_range_max": 28}),
        ("EURUSD=X", "1h", 60, "hw_range", {"atr_sl_mult": 3.0, "atr_tp_mult": 0.45, "rsi_oversold": 40, "rsi_overbought": 65, "adx_range_max": 24}),
        ("EURUSD=X", "1h", 90, "hw_range", {"atr_sl_mult": 3.0, "atr_tp_mult": 0.45, "rsi_oversold": 40, "rsi_overbought": 65, "adx_range_max": 24}),
        ("GC=F", "1h", 60, "hw_range", {"atr_sl_mult": 2.0, "atr_tp_mult": 0.6, "rsi_oversold": 30, "rsi_overbought": 70, "adx_range_max": 28}),
        ("GC=F", "15m", 30, "hw_range", {"atr_sl_mult": 2.5, "atr_tp_mult": 0.5, "rsi_oversold": 30, "rsi_overbought": 70, "adx_range_max": 28}),
    ]

    print(f"TUNE_5H_START duration={DURATION_SEC}s report={REPORT}", flush=True)

    def evaluate(sym, tf, days, algo, params: dict, do_neighbor: bool = True):
        nonlocal best
        key = hashlib.md5(
            f"{sym}|{tf}|{days}|{algo}|{json.dumps(params, sort_keys=True)}".encode()
        ).hexdigest()
        if key in seen:
            return
        seen.add(key)
        state["trials"] += 1
        raw = get_raw(sym, tf, days)
        if raw is None or len(raw) < 80:
            return
        end = raw["time"].iloc[-1]
        import pandas as pd

        start = end - pd.Timedelta(days=days)
        chunk = raw[raw["time"] >= start]
        if len(chunk) < 60:
            return
        cfg = base_cfg(sym, tf, days, algo)
        cfg.update(params)
        try:
            res = run_backtest(chunk, cfg)
        except Exception as e:
            state["bt_errors"] += 1
            if state["bt_errors"] <= 20:
                print(f"BT_FAIL {sym} {tf} {algo}: {e}", flush=True)
            return
        if res.total_trades < 8:
            return
        span = max((chunk["time"].iloc[-1] - chunk["time"].iloc[0]).total_seconds() / 86400.0, 0.01)
        max_day, days_ge = daily_stats(res.trades)
        wr = float(res.win_rate)
        eq = float(res.final_equity)
        ppd = float(res.net_pnl) / span
        neigh = neighbor_score(raw, cfg, days) if (do_neighbor and wr >= 95) else wr
        sc = compute_score(wr, res.total_trades, eq, ppd, neigh)
        hit = Hit(
            symbol=sym,
            tf=tf,
            days=days,
            algo=algo,
            params={k: (round(v, 4) if isinstance(v, float) else v) for k, v in params.items()},
            n=int(res.total_trades),
            wr=wr,
            er=float(res.expectancy_r),
            eq=eq,
            ppd=ppd,
            max_day=max_day,
            days_ge_100=days_ge,
            span=span,
            halt=res.halt_reason or "none",
            score=sc,
        )
        if wr >= 99.999:
            state["hits_100"] += 1
            hits.append(hit)
            print(
                f"HIT100 {sym:10} {tf:4} {algo:14} n={hit.n:3} eq={eq:.2f} "
                f"$/d={ppd:.2f} maxDay={max_day:.2f} neighWR={neigh:.1f}",
                flush=True,
            )
        elif wr >= 95 and ppd >= 5:
            hits.append(hit)
            print(
                f"NEAR   {sym:10} {tf:4} {algo:14} wr={wr:.1f} n={hit.n:3} "
                f"eq={eq:.2f} $/d={ppd:.2f}",
                flush=True,
            )
        if best is None or hit.score > best.score:
            best = hit
            print(
                f"NEW_BEST score={sc:.1f} wr={wr:.1f} eq={eq:.2f} $/d={ppd:.2f} "
                f"{sym} {tf} {algo}",
                flush=True,
            )
            write_progress(state, hits, best)

    # Phase 0: seeds
    for sym, tf, days, algo, p in seeds:
        evaluate(sym, tf, days, algo, p, do_neighbor=True)

    last_write = 0.0
    # Structured gold grid first ~45 min worth, then random forever
    gold_grid = list(
        itertools.product(
            [45, 60, 75],
            [1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
            [0.25, 0.35, 0.45, 0.55, 0.6, 0.7],
            [25, 30, 35, 40],
            [60, 65, 70, 75],
            [22, 26, 28, 32],
        )
    )
    rng.shuffle(gold_grid)
    gi = 0

    while time.time() < deadline:
        elapsed = time.time() - t0
        state["elapsed_sec"] = elapsed
        # Phases by time
        if elapsed < 90 * 60:
            state["phase"] = "gold_grid"
            if gi < len(gold_grid):
                days, sl, tp, os_, ob, adx = gold_grid[gi]
                gi += 1
                evaluate(
                    "GC=F",
                    "1h",
                    days,
                    "hw_range",
                    {
                        "atr_sl_mult": sl,
                        "atr_tp_mult": tp,
                        "rsi_oversold": os_,
                        "rsi_overbought": ob,
                        "adx_range_max": adx,
                    },
                    do_neighbor=True,
                )
            else:
                state["phase"] = "gold_random"
                p = sample_params(rng, "gold_focus")
                evaluate("GC=F", rng.choice(["1h", "15m"]), rng.choice(LOOKBACKS), "hw_range", p)
        elif elapsed < 180 * 60:
            state["phase"] = "fx_hw_range"
            p = sample_params(rng, "gold_focus")
            evaluate(
                rng.choice(["EURUSD=X", "GBPUSD=X", "AUDUSD=X"]),
                rng.choice(["1h", "15m"]),
                rng.choice(LOOKBACKS),
                "hw_range",
                p,
                do_neighbor=False,
            )
        elif elapsed < 240 * 60:
            state["phase"] = "book_algos"
            p = sample_params(rng, "wide")
            evaluate(
                rng.choice(SYMBOLS),
                rng.choice(TFS),
                rng.choice([30, 45, 60]),
                rng.choice(ALGOS),
                p,
                do_neighbor=False,
            )
        else:
            state["phase"] = "exploit_best"
            # Mutate around best
            if best is None:
                p = sample_params(rng, "gold_focus")
                evaluate("GC=F", "1h", 45, "hw_range", p)
            else:
                p = dict(best.params)
                for k in list(p.keys()):
                    if rng.random() < 0.4:
                        if isinstance(p[k], float):
                            p[k] = max(0.05, p[k] * rng.uniform(0.85, 1.15))
                        elif isinstance(p[k], int):
                            p[k] = max(1, int(p[k] + rng.randint(-3, 3)))
                evaluate(
                    best.symbol,
                    best.tf,
                    rng.choice([best.days - 15, best.days, best.days + 15, best.days + 30]),
                    best.algo,
                    p,
                    do_neighbor=True,
                )

        if time.time() - last_write > 60:
            write_progress(state, hits, best)
            last_write = time.time()
            print(
                f"PROGRESS h={elapsed/3600:.2f} trials={state['trials']} "
                f"hits100={state['hits_100']} best_eq={best.eq if best else 0:.2f} "
                f"phase={state['phase']}",
                flush=True,
            )

    write_progress(state, hits, best)
    print(f"TUNE_5H_DONE trials={state['trials']} hits100={state['hits_100']}", flush=True)
    if best:
        print(f"BEST {best.symbol} {best.tf} {best.algo} wr={best.wr} eq={best.eq} $/d={best.ppd}", flush=True)


if __name__ == "__main__":
    main()
