#!/usr/bin/env python3
"""Fair bake-off of every Aegis signal on the same EURUSD 1h sample.

Ranks by expectancy and net PnL (Tharp), not win rate. Not a 100% WR hunt.
Yahoo 1h is not live M1 — results are a ranking, not a live guarantee.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.data import add_spread_proxy, fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategies_catalog import STRATEGIES, prepare_bakeoff
from aegis.strategy import prepare, signal_from_row

# Shared EURUSD 1h costs/risk. Conservative vs MetaQuotes 0-spread quotes.
BASE: dict = {
    "symbol": "EURUSD=X",
    "timeframe": "1h",
    "lookback_days": 400,
    "starting_equity": 10_000,
    "risk_percent": 0.5,
    "max_daily_loss_percent": 12.0,
    "max_total_drawdown_percent": 30.0,
    "max_positions": 1,
    "kill_switch": False,
    "pyramid_enabled": False,
    "spread_bps": 2.26,
    "slippage_bps": 0.4,
    "commission_round_trip_usd": 0.0,
    "session_start_utc": 7,
    "session_end_utc": 21,
    "ema_fast": 50,
    "ema_slow": 200,
    "atr_period": 14,
    "adx_period": 14,
    "adx_trend_threshold": 25,
    "adx_range_max": 22,
    "donchian_period": 55,
    "bb_period": 20,
    "bb_std": 2.0,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "atr_sl_mult": 2.5,
    "atr_tp_mult": 0.8,
    "atr_trail_mult": 3.0,
    "min_atr_pct": 0.0004,
    "min_rr": 1.5,
    "cost_buffer": 1.5,
    "firehose_pip_size": 0.0001,
    "jpy_pip_size": 0.01,
    "firehose_every_bar": False,
    "firehose_book_filter": False,
    "firehose_chart_read": False,
    "firehose_tp_pips": 16,
    "firehose_sl_pips": 8,
    "orb_bars": 2,
    "ib_bars": 4,
    "orb_max_atr": 2.5,
    "ntz_start_utc": 7,
    "ntz_end_utc": 8,
    "ntz_flatten_utc": 17,
    "ntz_min_atr": 0.3,
    "ntz_max_atr": 4.0,
    "ntz_asia_max_pct": 0.05,
    "ntz_max_trades_day": 0,
    "book_min_triggers": 1,
    "book_require_vwap": False,
    "book_adx_max": 50,
    "adx_min": 15,
    "rsi_pullback": 45,
    "rsi_pullback_hi": 55,
    "thomas_rr": 4.0,
    "ensemble_min_votes": 2,
    "ensemble_members": [
        "book_optimal",
        "breakout_adx",
        "trend_pullback",
        "hw_range",
    ],
    "er_period": 10,
    "pa_min_er": 0.30,
    "pa_allow_trend": True,
    "pa_allow_range": True,
    "pa_require_h1": True,
    "pa_elder_censor": True,
    "pa_allow_pin": True,
    "pa_allow_engulf": True,
    "pa_allow_retest": True,
    "pa_sl_buffer_pips": 1.0,
    "pa_max_sl_pips": 12.0,
    "pa_tp_mode": "r_multiple",
    "pa_tp_r": 4.0,
    "pa_zone_pips": 8.0,
    "high_risk_mode": "traditional",
    "high_risk_safe": True,
}


def score_row(row: dict, min_trades: int) -> float:
    if int(row["trades"]) < min_trades:
        return -1e9
    exp = float(row["expectancy_r"])
    pf = float(row["profit_factor"])
    if pf == float("inf"):
        pf = 5.0
    dd = float(row["max_dd_pct"])
    pnl = float(row["net_pnl"])
    trades = min(int(row["trades"]), 200)
    if pnl <= 0:
        return exp * 50.0 + pf * 5.0 - dd
    return 1000.0 + exp * 100.0 + pf * 15.0 - dd + 0.05 * trades


def run_one(df: pd.DataFrame, cfg: dict, *, prepare_fn=None, signal_fn=None) -> dict:
    res = run_backtest(df, cfg, prepare_fn=prepare_fn, signal_fn=signal_fn)
    pf = res.profit_factor
    return {
        "trades": int(res.total_trades),
        "win_rate": round(res.win_rate, 2),
        "profit_factor": round(pf, 3) if pf != float("inf") else float("inf"),
        "max_dd_pct": round(res.max_drawdown_pct, 2),
        "expectancy_r": round(res.expectancy_r, 3),
        "net_pnl": round(res.net_pnl, 2),
        "final_equity": round(res.final_equity, 2),
        "halt": res.halt_reason or "",
        "error": "",
    }


def _jobs(cfg0: dict) -> list[tuple[str, str, dict, object, object]]:
    jobs: list[tuple[str, str, dict, object, object]] = []
    skip_dup = {"ensemble_optimal", "all_books"}
    for name in ALGOS:
        if name in skip_dup:
            continue
        jobs.append((name, "algo", {**cfg0, "signal_mode": name, "algo": name}, prepare, signal_from_row))
    jobs.append(
        (
            "ensemble_optimal",
            "algo",
            {**cfg0, "signal_mode": "ensemble", "algo": "ensemble", "ensemble_min_votes": 2},
            prepare,
            signal_from_row,
        )
    )
    jobs.append(
        (
            "firehose_every_bar",
            "algo",
            {
                **cfg0,
                "signal_mode": "firehose",
                "algo": "firehose",
                "firehose_every_bar": True,
                "min_rr": 0.01,
            },
            prepare,
            signal_from_row,
        )
    )
    jobs.append(
        ("scalper_2h", "algo", {**cfg0, "signal_mode": "scalper_2h", "algo": "scalper_2h"}, prepare, signal_from_row)
    )
    jobs.append(("aegis_regime", "algo", {**cfg0, "signal_mode": "", "algo": ""}, prepare, signal_from_row))
    for spec in STRATEGIES:
        jobs.append((spec.id, "catalog", {**cfg0, "signal_mode": spec.id}, prepare_bakeoff, spec.signal_fn))
    return jobs


def load_mt5_frame(eng, symbol: str, timeframe: str, lookback_days: int) -> tuple[pd.DataFrame, dict]:
    spec = eng.symbol_spec(symbol)
    bars = eng.bars(symbol, timeframe, lookback_days)
    df = pd.DataFrame(
        [
            {
                "time": pd.Timestamp(b.time),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ]
    )
    if df.empty:
        raise RuntimeError(f"No MT5 bars for {symbol} {timeframe}")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    mid = (spec["bid"] + spec["ask"]) / 2.0 if spec["bid"] and spec["ask"] else 0.0
    spread_bps = (spec["spread_price"] / mid * 10000.0) if mid > 0 else float(BASE["spread_bps"])
    lots = 0.01
    meta = {
        "symbol": spec["name"],
        "spread_bps": float(spread_bps),
        "spread_price": float(spec["spread_price"]),
        "bid": float(spec["bid"]),
        "ask": float(spec["ask"]),
        "fixed_units": lots * float(spec["trade_contract_size"]),
        "lots": lots,
        "contract": float(spec["trade_contract_size"]),
    }
    return df, meta


def bake_one_frame(df: pd.DataFrame, cfg0: dict, min_trades: int, source: str) -> pd.DataFrame:
    print(f"Data: {len(df)} bars | {cfg0['symbol']} {cfg0['timeframe']} source={source}")
    rows: list[dict] = []
    for sid, family, cfg, prep_fn, sig_fn in _jobs(cfg0):
        print(f"  running {sid} ...", flush=True)
        try:
            row = run_one(df, cfg, prepare_fn=prep_fn, signal_fn=sig_fn)
        except Exception as exc:
            row = {
                "trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_dd_pct": 0.0,
                "expectancy_r": 0.0,
                "net_pnl": 0.0,
                "final_equity": float(cfg0["starting_equity"]),
                "halt": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
            traceback.print_exc()
        row["id"] = sid
        row["family"] = family
        row["liveable"] = family == "algo"
        row["score"] = round(score_row(row, min_trades), 2)
        rows.append(row)
        err = f" ERR={row['error']}" if row["error"] else ""
        print(
            f"    trades={row['trades']:4d}  WR={row['win_rate']:6.2f}%  "
            f"E[R]={row['expectancy_r']:6.3f}  PnL={row['net_pnl']:9.2f}  "
            f"score={row['score']}{err}",
            flush=True,
        )
    return pd.DataFrame(rows).sort_values(
        ["score", "net_pnl", "expectancy_r"], ascending=[False, False, False]
    ).reset_index(drop=True)


def write_report(table: pd.DataFrame, cfg0: dict, df: pd.DataFrame, min_trades: int, source: str, extra: str) -> dict:
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{source}_{cfg0['timeframe']}".replace("=", "")
    csv_path = out_dir / f"all_algos_bakeoff_{tag}.csv"
    md_path = out_dir / f"ALL_ALGOS_BAKEOFF_{tag.upper()}.md"
    table.to_csv(csv_path, index=False)
    live = table[table["liveable"] & (table["trades"] >= min_trades) & (table["error"] == "")]
    profitable = live[live["net_pnl"] > 0]
    pool = profitable if not profitable.empty else live
    winner = pool.iloc[0] if not pool.empty else table.iloc[0]
    lines = [
        f"# All-algos bake-off ({source} {cfg0['timeframe']})",
        "",
        f"Symbol: `{cfg0['symbol']}` · Timeframe: `{cfg0['timeframe']}` · Bars: `{len(df)}` · Source: `{source}`",
        "",
        extra,
        "",
        "Ranked by expectancy and net PnL (Tharp), not win rate. Not a 100% WR claim.",
        "",
        f"**Live winner (≥{min_trades} trades): `{winner['id']}`**",
        "",
        f"- Trades: **{winner['trades']}**",
        f"- Win rate: **{winner['win_rate']}%** (not the ranking key)",
        f"- Expectancy R: **{winner['expectancy_r']}**",
        f"- Profit factor: **{winner['profit_factor']}**",
        f"- Max DD: **{winner['max_dd_pct']}%**",
        f"- Net PnL: **{winner['net_pnl']}**",
        "",
        "## Ranked results",
        "",
        "| Rank | ID | Family | Trades | WR% | E[R] | PF | MaxDD% | Net PnL | Score |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, r in table.iterrows():
        pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.3f}"
        lines.append(
            f"| {i + 1} | `{r['id']}` | {r['family']} | {r['trades']} | {r['win_rate']:.2f} | "
            f"{r['expectancy_r']:.3f} | {pf} | {r['max_dd_pct']:.2f} | {r['net_pnl']:.2f} | {r['score']:.2f} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n=== RANKING ===")
    print(table[["id", "family", "trades", "win_rate", "expectancy_r", "net_pnl", "score"]].to_string(index=False))
    print(f"\nLive winner: {winner['id']}")
    print(f"Report: {md_path}")
    print(f"WINNER={winner['id']}")
    return {"id": str(winner["id"]), "trades": int(winner["trades"]), "net_pnl": float(winner["net_pnl"]), "expectancy_r": float(winner["expectancy_r"]), "win_rate": float(winner["win_rate"]), "md": str(md_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bake off every Aegis algo")
    parser.add_argument("--min-trades", type=int, default=10)
    parser.add_argument("--lookback-days", type=int, default=400)
    parser.add_argument("--source", choices=["yahoo", "mt5"], default="yahoo")
    parser.add_argument("--timeframes", default="1h", help="Comma-separated, e.g. 1h,15m")
    parser.add_argument("--shutdown-mt5", action="store_true", help="Call mt5.shutdown after fetch (kills other Python MT5 users)")
    args = parser.parse_args()
    tfs = [t.strip() for t in str(args.timeframes).split(",") if t.strip()]

    eng = None
    acct = None
    mt5_meta: dict = {}
    if args.source == "mt5":
        from aegis.config import load_config
        from aegis.engines.mt5 import MT5Engine

        live_cfg = load_config(ROOT / "config_mt5_demo_best.yaml")
        live_cfg["allow_live"] = False
        eng = MT5Engine(live_cfg)
        eng.connect()
        acct = eng.account()
        if not acct.is_paper:
            raise SystemExit("Refusing bake-off on a non-demo MT5 account")
        print(f"MT5 demo {acct.account_id} equity={acct.equity:.2f} — not shutting down the terminal")

    try:
        for tf in tfs:
            cfg0 = {**BASE, "lookback_days": int(args.lookback_days), "timeframe": tf}
            extra = "Yahoo 1h is not live M1."
            if args.source == "mt5":
                lookback = int(args.lookback_days)
                if tf in {"15m", "m15"}:
                    lookback = min(lookback, 180)
                elif tf in {"1m", "m1"}:
                    lookback = min(lookback, 14)
                df, mt5_meta = load_mt5_frame(eng, "EURUSD", tf, lookback)
                cfg0["symbol"] = mt5_meta["symbol"]
                cfg0["spread_bps"] = max(mt5_meta["spread_bps"], 0.2)
                cfg0["fixed_units"] = mt5_meta["fixed_units"]
                cfg0["starting_equity"] = float(acct.equity) if acct is not None else 100.0
                extra = (
                    f"MT5 demo bars + live spread snapshot {mt5_meta['spread_price']:.5f} "
                    f"({cfg0['spread_bps']:.3f} bps). Size = {mt5_meta['lots']} lots "
                    f"({int(mt5_meta['fixed_units'])} units). Did not call mt5.shutdown()."
                )
            else:
                df = fetch_ohlcv(cfg0["symbol"], cfg0["timeframe"], int(cfg0["lookback_days"]))
                df = add_spread_proxy(df, float(cfg0["spread_bps"]))
            table = bake_one_frame(df, cfg0, args.min_trades, args.source)
            write_report(table, cfg0, df, args.min_trades, args.source, extra)
    finally:
        if eng is not None and args.shutdown_mt5:
            eng.disconnect()


if __name__ == "__main__":
    main()

    for name in ALGOS:
        if name in skip_dup:
            continue
        jobs.append((name, "algo", {**cfg0, "signal_mode": name, "algo": name}, prepare, signal_from_row))

    jobs.append(
        (
            "ensemble_optimal",
            "algo",
            {**cfg0, "signal_mode": "ensemble", "algo": "ensemble", "ensemble_min_votes": 2},
            prepare,
            signal_from_row,
        )
    )
    jobs.append(
        (
            "firehose_every_bar",
            "algo",
            {
                **cfg0,
                "signal_mode": "firehose",
                "algo": "firehose",
                "firehose_every_bar": True,
                "min_rr": 0.01,
            },
            prepare,
            signal_from_row,
        )
    )
    jobs.append(
        ("scalper_2h", "algo", {**cfg0, "signal_mode": "scalper_2h", "algo": "scalper_2h"}, prepare, signal_from_row)
    )
    jobs.append(("aegis_regime", "algo", {**cfg0, "signal_mode": "", "algo": ""}, prepare, signal_from_row))

    for spec in STRATEGIES:
        jobs.append((spec.id, "catalog", {**cfg0, "signal_mode": spec.id}, prepare_bakeoff, spec.signal_fn))

    rows: list[dict] = []
    for sid, family, cfg, prep_fn, sig_fn in jobs:
        print(f"  running {sid} ...", flush=True)
        try:
            row = run_one(df, cfg, prepare_fn=prep_fn, signal_fn=sig_fn)
        except Exception as exc:
            row = {
                "trades": 0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "max_dd_pct": 0.0,
                "expectancy_r": 0.0,
                "net_pnl": 0.0,
                "final_equity": float(cfg0["starting_equity"]),
                "halt": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
            traceback.print_exc()
        row["id"] = sid
        row["family"] = family
        row["liveable"] = family == "algo"
        row["score"] = round(score_row(row, args.min_trades), 2)
        rows.append(row)
        err = f" ERR={row['error']}" if row["error"] else ""
        print(
            f"    trades={row['trades']:4d}  WR={row['win_rate']:6.2f}%  "
            f"E[R]={row['expectancy_r']:6.3f}  PnL={row['net_pnl']:9.2f}  "
            f"score={row['score']}{err}",
            flush=True,
        )

    table = pd.DataFrame(rows).sort_values(
        ["score", "net_pnl", "expectancy_r"], ascending=[False, False, False]
    ).reset_index(drop=True)

    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "all_algos_bakeoff.csv"
    md_path = out_dir / "ALL_ALGOS_BAKEOFF.md"
    table.to_csv(csv_path, index=False)

    live = table[table["liveable"] & (table["trades"] >= args.min_trades) & (table["error"] == "")]
    profitable = live[live["net_pnl"] > 0]
    pool = profitable if not profitable.empty else live
    winner = pool.iloc[0] if not pool.empty else table.iloc[0]

    lines = [
        "# All-algos bake-off",
        "",
        f"Symbol: `{cfg0['symbol']}` · Timeframe: `{cfg0['timeframe']}` · Bars: `{len(df)}`",
        "",
        "Same data, same risk, same costs. Ranked by expectancy and net PnL (Tharp), not win rate.",
        "Yahoo 1h is not live M1. Not a 100% WR claim. Not a live profit guarantee.",
        "",
        f"**Live winner (≥{args.min_trades} trades): `{winner['id']}`**",
        "",
        f"- Trades: **{winner['trades']}**",
        f"- Win rate: **{winner['win_rate']}%** (not the ranking key)",
        f"- Expectancy R: **{winner['expectancy_r']}**",
        f"- Profit factor: **{winner['profit_factor']}**",
        f"- Max DD: **{winner['max_dd_pct']}%**",
        f"- Net PnL: **{winner['net_pnl']}** on $10k sample",
        "",
        "## Ranked results",
        "",
        "| Rank | ID | Family | Trades | WR% | E[R] | PF | MaxDD% | Net PnL | Score |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, r in table.iterrows():
        pf = "inf" if r["profit_factor"] == float("inf") else f"{r['profit_factor']:.3f}"
        lines.append(
            f"| {i + 1} | `{r['id']}` | {r['family']} | {r['trades']} | {r['win_rate']:.2f} | "
            f"{r['expectancy_r']:.3f} | {pf} | {r['max_dd_pct']:.2f} | {r['net_pnl']:.2f} | {r['score']:.2f} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n=== RANKING ===")
    print(table[["id", "family", "trades", "win_rate", "expectancy_r", "net_pnl", "score"]].to_string(index=False))
    print(f"\nLive winner: {winner['id']}")
    print(f"Report: {md_path}")
    print(f"CSV:    {csv_path}")
    print(f"WINNER={winner['id']}")


if __name__ == "__main__":
    main()
