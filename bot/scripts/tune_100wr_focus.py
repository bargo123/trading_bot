#!/usr/bin/env python3
"""Focused 100% WR tuner with incremental saves (params included).

Measured-only: does not claim forever 100% WR.
"""
from __future__ import annotations

import itertools
import json
import random
import time
from pathlib import Path

import yaml

from aegis.backtest import format_report, run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategy import prepare

ROOT = Path(__file__).resolve().parents[1]
random.seed(7)
t0 = time.time()
BUDGET_SEC = 20 * 60
cache: dict = {}
hits: list[dict] = []
tested = 0
best_score = (-1, -1.0, -1.0)  # n, er, pnl


def get_df(sym, tf, days, sp=0.8):
    k = (sym, tf, days, sp)
    if k not in cache:
        cache[k] = add_spread_proxy(fetch_ohlcv(sym, tf, days), sp)
    return cache[k]


base = {
    "symbol": "EURUSD=X",
    "timeframe": "1h",
    "lookback_days": 60,
    "starting_equity": 10000,
    "risk_percent": 0.5,
    "high_risk_mode": "traditional",
    "high_risk_safe": True,
    "allow_unsafe_high_risk": False,
    "hr_equity_floor_frac": 0.0,
    "hr_max_consecutive_losses": 999,
    "hr_use_risk_bankroll": False,
    "spread_bps": 0.8,
    "slippage_bps": 0.4,
    "cost_buffer": 1.0,
    "session_start_utc": 0,
    "session_end_utc": 21,
    "adx_period": 14,
    "adx_trend_threshold": 99,
    "adx_range_max": 24,
    "ema_fast": 50,
    "ema_slow": 200,
    "atr_period": 14,
    "atr_trail_mult": 3.0,
    "bb_period": 30,
    "bb_std": 1.8,
    "rsi_period": 14,
    "rsi_oversold": 35,
    "rsi_overbought": 70,
    "atr_sl_mult": 3.5,
    "atr_tp_mult": 0.4,
    "min_rr": 0.01,
    "min_atr_pct": 0.0004,
    "max_positions": 1,
    "pyramid_enabled": False,
    "ntz_max_trades_day": 0,
    "mode": "paper",
    "tp_mode": "atr",
    "signal_mode": "hw_range",
    "algo": "hw_range",
    "donchian_period": 55,
    "kill_switch": False,
}


def timed_out():
    return (time.time() - t0) >= BUDGET_SEC


def score_tuple(h):
    return (h.get("perfect_windows", 0), h["n"], h["er"], h["pnl"])


def save_best(h, tag="interim"):
    cfg = dict(h["cfg"])
    cfg.update(
        starting_equity=100,
        risk_percent=100,
        high_risk_mode="traditional",
        high_risk_safe=False,
        allow_unsafe_high_risk=True,
        hr_risk_max_cap=100,
        hr_equity_floor_frac=0.01,
        hr_max_consecutive_losses=999,
        max_daily_loss_percent=100,
        max_total_drawdown_percent=100,
        pyramid_enabled=False,
        test_name="tuned_100wr",
        signal_mode="hw_range",
        algo="hw_range",
    )
    (ROOT / "config_tuned_100wr.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    df = get_df(cfg["symbol"], cfg["timeframe"], int(cfg["lookback_days"]))
    res = run_backtest(df, cfg, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
    report = [
        "# One-hour 100% WR tuning",
        "",
        f"- Source: focused tuner (`{tag}`)",
        f"- Elapsed: **{(time.time()-t0)/60:.1f} min**",
        f"- Configs tested (this process): **{tested}**",
        f"- Measured 100% WR hits (n≥5): **{len(hits)}**",
        "",
        "## Best pick (measured)",
        f"- {h['sym']} {h['tf']} {h['days']}d · trades **{h['n']}** · WR **{h['wr']:.1f}%** · E[R] **{h['er']:.3f}**",
        f"- Params: SL={h['sl']} ATR · TP={h['tp']} ATR · RSI {h['os']}/{h['ob']} · ADX<{h['adx']} · BB {h['bb']}/{h['bbstd']}",
        f"- Neighbor windows with 100% WR: **{h.get('perfect_windows', '?')}** · avg WR nearby **{h.get('avg_wr_near', 0):.1f}%**",
        f"- $100 all-in verify: **${res.final_equity:.2f}** · trades {res.total_trades} · WR {res.win_rate:.1f}% · E[R] {res.expectancy_r:.3f}",
        "",
        "Config: `config_tuned_100wr.yaml`",
        "",
        "> Measured on historical yfinance bars only. Not a claim of future or forever 100% WR.",
        "",
    ]
    if h.get("windows"):
        report.append("## Neighbor windows")
        for lb, n, wr, er, pnl in h["windows"]:
            report.append(f"- {lb}d: n={n} WR={wr:.1f}% E[R]={er:.3f} pnl={pnl:.2f}")
        report.append("")
    (ROOT / "reports" / "TUNE_100WR_1H.md").write_text("\n".join(report) + "\n")
    print(
        f"SAVED best n={h['n']} E={h['er']:.3f} $100→${res.final_equity:.2f} perfect={h.get('perfect_windows')}",
        flush=True,
    )
    return res


def neighbor_validate(h):
    cfg = dict(h["cfg"])
    scores = []
    for lb in sorted({max(30, h["days"] - 15), h["days"], h["days"] + 15, h["days"] + 30}):
        c = dict(cfg)
        c["lookback_days"] = lb
        try:
            df = get_df(c["symbol"], c["timeframe"], lb)
        except Exception:
            continue
        res = run_backtest(df, c, prepare_fn=prepare, signal_fn=ALGOS["hw_range"])
        scores.append((lb, res.total_trades, res.win_rate, res.expectancy_r, res.net_pnl))
    perfect = sum(1 for s in scores if s[1] >= 5 and s[2] >= 99.999)
    avg_wr = sum(s[2] for s in scores) / max(len(scores), 1)
    h2 = dict(h)
    h2["windows"] = scores
    h2["perfect_windows"] = perfect
    h2["avg_wr_near"] = avg_wr
    return h2


def eval_cfg(cfg, tag=""):
    global tested, best_score
    if timed_out():
        return None
    sym, tf, days = cfg["symbol"], cfg["timeframe"], int(cfg["lookback_days"])
    try:
        df = get_df(sym, tf, days, float(cfg.get("spread_bps", 0.8)))
    except Exception:
        return None
    algo = cfg["algo"]
    if algo not in ALGOS:
        return None
    res = run_backtest(df, cfg, prepare_fn=prepare, signal_fn=ALGOS[algo])
    tested += 1
    if res.total_trades >= 5 and res.win_rate >= 99.999:
        hit = {
            "tag": tag,
            "sym": sym,
            "tf": tf,
            "days": days,
            "algo": algo,
            "n": res.total_trades,
            "wr": res.win_rate,
            "er": res.expectancy_r,
            "pnl": res.net_pnl,
            "eq": res.final_equity,
            "sl": cfg.get("atr_sl_mult"),
            "tp": cfg.get("atr_tp_mult"),
            "os": cfg.get("rsi_oversold"),
            "ob": cfg.get("rsi_overbought"),
            "adx": cfg.get("adx_range_max"),
            "bb": cfg.get("bb_period"),
            "bbstd": cfg.get("bb_std"),
            "cfg": dict(cfg),
        }
        hits.append(hit)
        sc = (hit["n"], hit["er"], hit["pnl"])
        print(
            f"HIT n={hit['n']:3d} E={hit['er']:.3f} pnl={hit['pnl']:7.2f} "
            f"sl={hit['sl']} tp={hit['tp']} rsi={hit['os']}/{hit['ob']} "
            f"adx<{hit['adx']} {sym} {days}d {tag}",
            flush=True,
        )
        if sc > best_score:
            best_score = sc
            # quick validate + save when we beat prior n/E/pnl
            hv = neighbor_validate(hit)
            save_best(hv, tag=f"beat-{tag}")
        return hit
    return None


def main():
    print("Prefetch…", flush=True)
    for sym in ["EURUSD=X", "GBPUSD=X"]:
        for days in [45, 60, 75, 90]:
            get_df(sym, "1h", days)
            print(f"  {sym} 1h {days}d ok", flush=True)

    # Dense around high-n region seen in long hunt (EURUSD 45–90d, wide SL, tiny TP)
    print("\n=== Focus dense ===", flush=True)
    grid = list(
        itertools.product(
            ["EURUSD=X", "GBPUSD=X"],
            [45, 60, 75, 90],
            [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5],
            [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
            [30, 35, 40],
            [65, 70, 75],
            [20, 22, 24, 26, 28],
            [1.6, 1.8, 2.0],
            [24, 28, 30],
        )
    )
    random.shuffle(grid)
    print(f"focus grid {len(grid)}", flush=True)
    for i, (sym, lb, sl, tp, os_, ob_, adx, bbstd, bb) in enumerate(grid):
        if timed_out():
            print("budget hit dense", flush=True)
            break
        cfg = dict(base)
        cfg.update(
            symbol=sym,
            lookback_days=lb,
            atr_sl_mult=sl,
            atr_tp_mult=tp,
            rsi_oversold=os_,
            rsi_overbought=ob_,
            adx_range_max=adx,
            bb_std=bbstd,
            bb_period=bb,
        )
        eval_cfg(cfg, "focus")
        if (i + 1) % 150 == 0:
            print(f"…{i+1} tested={tested} hits={len(hits)} elapsed={time.time()-t0:.0f}s", flush=True)

    # Mutate top by n, er
    print("\n=== Mutate top ===", flush=True)
    seeds = sorted(hits, key=lambda h: (h["n"], h["er"], h["pnl"]), reverse=True)[:30]
    for seed in seeds:
        if timed_out():
            break
        for sess in [(0, 21), (7, 17), (8, 16), (12, 20)]:
            for buf in [0.85, 1.0, 1.15]:
                if timed_out():
                    break
                cfg = dict(seed["cfg"])
                cfg.update(
                    session_start_utc=sess[0],
                    session_end_utc=sess[1],
                    cost_buffer=buf,
                    atr_tp_mult=round(float(cfg["atr_tp_mult"]) + random.choice([-0.05, 0, 0.05]), 3),
                    atr_sl_mult=round(float(cfg["atr_sl_mult"]) + random.choice([-0.5, 0, 0.5]), 2),
                )
                eval_cfg(cfg, "mutate")

    # Final rank by neighbor robustness
    print("\n=== Final neighbor rank ===", flush=True)
    ranked = sorted(hits, key=lambda h: (h["n"], h["er"], h["pnl"]), reverse=True)
    uniq, seen = [], set()
    for h in ranked:
        key = (h["sym"], h["days"], h["sl"], h["tp"], h["os"], h["ob"], h["adx"], h["bb"], h["bbstd"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
        if len(uniq) >= 20:
            break

    validated = []
    for h in uniq:
        if timed_out():
            break
        hv = neighbor_validate(h)
        validated.append(hv)
        print(
            f"validate n={h['n']} perfect={hv['perfect_windows']}/{len(hv['windows'])} "
            f"avgWR={hv['avg_wr_near']:.1f}% sl={h['sl']} tp={h['tp']}",
            flush=True,
        )

    validated.sort(key=score_tuple, reverse=True)
    best = validated[0] if validated else (uniq[0] if uniq else None)
    if best:
        res = save_best(best, tag="final")
        print("\nBEST VERIFY $100:", format_report(res), flush=True)
    (ROOT / "reports" / "tune_100wr_hits.json").write_text(
        json.dumps(
            [
                {k: v for k, v in h.items() if k != "cfg"}
                for h in sorted(hits, key=lambda x: (x["n"], x["er"]), reverse=True)[:100]
            ],
            indent=2,
        )
    )
    print(
        f"\nDONE elapsed={(time.time()-t0)/60:.1f}min tested={tested} hits={len(hits)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
