#!/usr/bin/env python3
"""Benchmark every Aegis algorithm and tune CAFB without holdout peeking."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.basket_backtest import run_basket_backtest
from aegis.cafb import prepare_cafb, sig_cafb
from aegis.data import fetch_ohlcv
from aegis.session_algos import ALGOS
from aegis.strategies_catalog import STRATEGIES, prepare_bakeoff
from aegis.strategy import prepare, signal_from_row, signal_scalper_2h

CACHE = ROOT / "data" / "cafb_snapshots"
REPORT = ROOT / "reports" / "CAFB_BASKET.md"
DETAILS = ROOT / "reports" / "cafb_benchmark_results.csv"
SEARCH = ROOT / "reports" / "cafb_search_results.csv"
TUNED = ROOT / "config_cafb_basket.tuned.yaml"


@dataclass(frozen=True)
class Case:
    name: str
    prepare_fn: Callable
    signal_fn: Callable
    updates: dict[str, Any]


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("=", "_").replace("/", "_")


def load_or_fetch(symbol: str, timeframe: str, days: int, refresh: bool) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    stem = CACHE / f"{_safe_symbol(symbol)}_{timeframe}_{days}d"
    csv_path = stem.with_suffix(".csv")
    meta_path = stem.with_suffix(".json")
    if csv_path.exists() and meta_path.exists() and not refresh:
        df = pd.read_csv(csv_path, parse_dates=["time"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df.attrs.update(json.loads(meta_path.read_text()))
        return df
    last_error = None
    for attempt in range(3):
        try:
            df = fetch_ohlcv(symbol, timeframe, days)
            break
        except Exception as exc:  # network/provider retries are recorded, not hidden
            last_error = exc
            if attempt < 2:
                time.sleep(2 + attempt)
    else:
        raise RuntimeError(f"{symbol} {timeframe}: {last_error}")
    meta = dict(df.attrs)
    meta.update(
        {
            "rows": len(df),
            "start_utc": str(df["time"].iloc[0]),
            "end_utc": str(df["time"].iloc[-1]),
            "fetched_utc": str(pd.Timestamp.now(tz="UTC")),
        }
    )
    df.to_csv(csv_path, index=False)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    return df


def get_data(symbols: list[str], timeframe: str, days: int, refresh: bool) -> dict[str, pd.DataFrame]:
    out = {}
    for symbol in symbols:
        try:
            df = load_or_fetch(symbol, timeframe, days, refresh)
            if len(df) >= 300:
                out[symbol] = df
                print(f"DATA {timeframe:>2} {symbol:10} {len(df):6d} {df.time.iloc[0]} -> {df.time.iloc[-1]}", flush=True)
        except Exception as exc:
            print(f"DATA ERROR {timeframe} {symbol}: {exc}", flush=True)
    if len(out) < 2:
        raise RuntimeError(f"Need at least two usable {timeframe} symbols; got {len(out)}")
    return out


def split_frames(frames: dict[str, pd.DataFrame], segment: str) -> dict[str, pd.DataFrame]:
    bounds = {"development": (0.0, 0.60), "validation": (0.60, 0.80), "holdout": (0.80, 1.0)}
    lo, hi = bounds[segment]
    out = {}
    for symbol, frame in frames.items():
        n = len(frame)
        a, b = int(n * lo), int(n * hi)
        out[symbol] = frame.iloc[a:b].copy().reset_index(drop=True)
    return out


def span_info(frames: dict[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp, float]:
    start = min(pd.Timestamp(df["time"].iloc[0]) for df in frames.values() if len(df))
    end = max(pd.Timestamp(df["time"].iloc[-1]) for df in frames.values() if len(df))
    days = max((end - start).total_seconds() / 86400.0, 1 / 1440)
    return start, end, days


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100 * max(0.0, center - half), 100 * min(1.0, center + half)


def metrics(name: str, segment: str, frames: dict[str, pd.DataFrame], res, cfg: dict[str, Any]) -> dict[str, Any]:
    start, end, days = span_info(frames)
    wins = int((res.trades["pnl"] > 0).sum()) if res.total_trades else 0
    ci_lo, ci_hi = wilson(wins, res.total_trades)
    pf = res.profit_factor
    per_symbol = {}
    if res.total_trades:
        per_symbol = {str(k): round(float(v), 6) for k, v in res.trades.groupby("symbol")["pnl"].sum().items()}
    return {
        "strategy": name,
        "segment": segment,
        "start_utc": str(start),
        "end_utc": str(end),
        "span_days": days,
        "trades": res.total_trades,
        "trades_per_day": res.total_trades / days,
        "win_rate": res.win_rate,
        "win_ci_low": ci_lo,
        "win_ci_high": ci_hi,
        "expectancy_r": res.expectancy_r,
        "profit_factor": pf,
        "max_drawdown_pct": res.max_drawdown_pct,
        "start_equity": float(cfg["starting_equity"]),
        "end_equity": res.final_equity,
        "net_pnl": res.net_pnl,
        "profit_per_day": res.net_pnl / days,
        "halt_reason": res.halt_reason or "none",
        "ambiguous_exits": res.ambiguous_exits,
        "skipped_entries": json.dumps(res.skipped_entries, sort_keys=True),
        "per_symbol_pnl": json.dumps(per_symbol, sort_keys=True),
    }


def base_config(config_path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(config_path.read_text())
    return {
        **cfg,
        "starting_equity": 100.0,
        "risk_percent": 2.0,
        "high_risk_mode": "traditional",
        "high_risk_safe": True,
        "hr_risk_max_cap": 20.0,
        "hr_max_consecutive_losses": 999,
        "hr_equity_floor_frac": 0.10,
        "max_positions": 2,
        "max_portfolio_heat_percent": 4.0,
        "max_currency_exposure": 2,
        "max_gross_leverage": 30.0,
        "min_units": 1000.0,
        "unit_step": 1000.0,
        "spread_bps": 0.6,  # 1.5x the config's 0.4-bps base assumption
        "slippage_bps": 0.3,
        "commission_bps": 0.0,
        "cost_buffer": 1.5,
        "max_hold_bars": 6,
        "donchian_period": 55,
        "atr_trail_mult": 3.0,
        "adx_trend_threshold": 25,
        "adx_range_max": 20,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "atr_sl_mult": 2.5,
        "atr_tp_mult": 0.8,
    }


def strategy_cases() -> list[Case]:
    cases: list[Case] = []
    seen: set[int] = set()
    for name, fn in ALGOS.items():
        if fn is sig_cafb or id(fn) in seen:
            continue
        seen.add(id(fn))
        cases.append(Case(name, prepare, fn, {"signal_mode": name, "algo": name}))
    cases.append(Case("generic_regime", prepare, signal_from_row, {"signal_mode": "generic", "algo": "generic"}))
    cases.append(Case("scalper_2h", prepare, signal_scalper_2h, {"signal_mode": "scalper_2h", "algo": "scalper_2h"}))
    for spec in STRATEGIES:
        cases.append(Case(f"catalog:{spec.id}", prepare_bakeoff, spec.signal_fn, {}))
    return cases


def benchmark_algorithms(
    raw: dict[str, pd.DataFrame],
    cfg: dict[str, Any],
    cases: list[Case] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for case in cases or strategy_cases():
        c = {**cfg, **case.updates}
        try:
            prepared = {s: case.prepare_fn(df, c) for s, df in raw.items()}
            for segment in ("development", "validation", "holdout"):
                sample = split_frames(prepared, segment)
                res = run_basket_backtest(
                    sample,
                    c,
                    prepare_fn=lambda df, _cfg: df,
                    signal_fn=case.signal_fn,
                )
                row = metrics(case.name, segment, sample, res, c)
                rows.append(row)
            val = rows[-2]
            print(
                f"ALGO {case.name:24} val n={val['trades']:4d} WR={val['win_rate']:6.2f}% "
                f"E[R]={val['expectancy_r']:+.3f} PF={val['profit_factor']:.2f} eq={val['end_equity']:.2f}",
                flush=True,
            )
        except Exception as exc:
            print(f"ALGO ERROR {case.name}: {type(exc).__name__}: {exc}", flush=True)
            rows.append({"strategy": case.name, "segment": "error", "error": f"{type(exc).__name__}: {exc}"})
    return rows


def tune_score(row: dict[str, Any], min_trades: int) -> float:
    if row["trades"] < min_trades or row["end_equity"] <= 0:
        return -1e9
    pf = min(float(row["profit_factor"]), 5.0) if math.isfinite(float(row["profit_factor"])) else 5.0
    positive = 40.0 if row["expectancy_r"] > 0 and pf > 1 else -80.0
    return (
        positive
        + 80.0 * row["expectancy_r"]
        + 8.0 * pf
        + 0.08 * row["win_rate"]
        + 0.20 * min(row["trades_per_day"], 100.0)
        - 0.50 * row["max_drawdown_pct"]
    )


def tune_cafb(raw: dict[str, pd.DataFrame], cfg: dict[str, Any], timeframe: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    context_minutes = 5 if timeframe == "1m" else 15
    min_trades = 5
    search_rows: list[dict[str, Any]] = []
    best: tuple[float, dict[str, Any], dict[str, pd.DataFrame]] | None = None
    feature_grid = itertools.product([3, 5, 8], [1.5, 2.5, 4.0], [12, 20])
    for box_bars, box_max_atr, adx_min in feature_grid:
        feature_cfg = {
            **cfg,
            "signal_mode": "cafb",
            "algo": "cafb",
            "cafb_context_minutes": context_minutes,
            "cafb_box_bars": box_bars,
            "cafb_box_min_atr": 0.1,
            "cafb_box_max_atr": box_max_atr,
            "cafb_htf_adx_min": adx_min,
        }
        prepared = {s: prepare_cafb(df, feature_cfg) for s, df in raw.items()}
        dev = split_frames(prepared, "development")
        val = split_frames(prepared, "validation")
        for min_rr, target_mode, allow_range in itertools.product(
            [0.1, 0.3], ["opposite", "extension"], [False, True]
        ):
            c = {
                **feature_cfg,
                "cafb_min_rr": min_rr,
                "cafb_target_mode": target_mode,
                "cafb_allow_range": allow_range,
            }
            dev_res = run_basket_backtest(dev, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_cafb)
            val_res = run_basket_backtest(val, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_cafb)
            dev_m = metrics("cafb", "development", dev, dev_res, c)
            val_m = metrics("cafb", "validation", val, val_res, c)
            score = tune_score(val_m, min_trades)
            row = {
                "timeframe": timeframe,
                "box_bars": box_bars,
                "box_max_atr": box_max_atr,
                "adx_min": adx_min,
                "min_rr": min_rr,
                "target_mode": target_mode,
                "allow_range": allow_range,
                "score": score,
                **{f"dev_{k}": v for k, v in dev_m.items() if k not in {"strategy", "segment"}},
                **{f"val_{k}": v for k, v in val_m.items() if k not in {"strategy", "segment"}},
            }
            search_rows.append(row)
            if best is None or score > best[0]:
                best = (score, c, prepared)
    assert best is not None
    best_score, best_cfg, best_prepared = best
    hold = split_frames(best_prepared, "holdout")
    hold_res = run_basket_backtest(hold, best_cfg, prepare_fn=lambda df, _cfg: df, signal_fn=sig_cafb)
    hold_m = metrics("cafb", "holdout", hold, hold_res, best_cfg)
    best_cfg = {**best_cfg, "_selection_score": best_score, "_holdout": hold_m}
    print(
        f"CAFB {timeframe} HOLDOUT n={hold_m['trades']} WR={hold_m['win_rate']:.2f}% "
        f"E[R]={hold_m['expectancy_r']:+.3f} PF={hold_m['profit_factor']:.2f} "
        f"DD={hold_m['max_drawdown_pct']:.2f}% eq={hold_m['end_equity']:.2f}",
        flush=True,
    )
    return best_cfg, search_rows


def final_stress(
    raw: dict[str, pd.DataFrame],
    selected: dict[str, Any],
    timeframe: str,
) -> list[dict[str, Any]]:
    cfg = {k: v for k, v in selected.items() if not k.startswith("_")}
    prepared = {s: prepare_cafb(df, cfg) for s, df in raw.items()}
    hold = split_frames(prepared, "holdout")
    rows = []
    for cost_scale in [1.0, 1.5, 2.0]:
        c = {
            **cfg,
            "spread_bps": 0.4 * cost_scale,
            "slippage_bps": 0.2 * cost_scale,
            "cost_buffer": cost_scale,
            "risk_percent": 2.0,
            "hr_risk_max_cap": 20.0,
        }
        res = run_basket_backtest(hold, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_cafb)
        row = metrics("cafb", f"holdout_cost_{cost_scale:.1f}x", hold, res, c)
        row.update({"timeframe": timeframe, "cost_scale": cost_scale, "risk_percent": 2.0})
        rows.append(row)
    for risk_pct in [1.0, 2.0, 5.0, 10.0, 20.0]:
        c = {
            **cfg,
            "spread_bps": 0.6,
            "slippage_bps": 0.3,
            "cost_buffer": 1.5,
            "risk_percent": risk_pct,
            "hr_risk_max_cap": risk_pct,
            "max_portfolio_heat_percent": max(2 * risk_pct, risk_pct),
            "max_daily_loss_percent": max(8.0, 2 * risk_pct),
            "max_total_drawdown_percent": max(30.0, 2 * risk_pct),
        }
        res = run_basket_backtest(hold, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_cafb)
        row = metrics("cafb", f"holdout_risk_{risk_pct:.0f}", hold, res, c)
        row.update({"timeframe": timeframe, "cost_scale": 1.5, "risk_percent": risk_pct})
        rows.append(row)
    return rows


def fmt_pf(value: Any) -> str:
    v = float(value)
    return "inf" if not math.isfinite(v) else f"{v:.2f}"


def metric_line(m: dict[str, Any]) -> str:
    return (
        f"n={m['trades']} · {m['trades_per_day']:.1f}/day · WR={m['win_rate']:.1f}% "
        f"(95% CI {m['win_ci_low']:.1f}–{m['win_ci_high']:.1f}%) · net E[R]={m['expectancy_r']:+.3f} · "
        f"PF={fmt_pf(m['profit_factor'])} · DD={m['max_drawdown_pct']:.1f}% · "
        f"$100→${m['end_equity']:.2f} · ${m['profit_per_day']:+.2f}/calendar day · "
        f"halt={m['halt_reason']} · ambiguous={m['ambiguous_exits']}"
    )


def write_report(
    symbols: list[str],
    data_m5: dict[str, pd.DataFrame],
    data_m1: dict[str, pd.DataFrame],
    benchmark: list[dict[str, Any]],
    selected_m5: dict[str, Any],
    selected_m1: dict[str, Any],
    stress: list[dict[str, Any]],
) -> None:
    valid_bench = [r for r in benchmark if r.get("segment") == "validation"]
    valid_bench.sort(key=lambda r: (r.get("expectancy_r", -999), r.get("trades", 0)), reverse=True)
    hold_m5 = selected_m5["_holdout"]
    hold_m1 = selected_m1["_holdout"]
    perfect = [m for m in [hold_m5, hold_m1] if m["trades"] > 0 and m["win_rate"] >= 99.999]
    verdict = (
        f"A 100% holdout result was observed on {', '.join(m['start_utc'] + ' to ' + m['end_utc'] for m in perfect)}. "
        "It is an observed sample, not a future guarantee."
        if perfect
        else "No tuned CAFB candidate achieved 100% WR on its frozen holdout after costs."
    )
    lines = [
        "# Cost-Aware Failed-Break Basket — measured results",
        "",
        f"Symbols: `{', '.join(symbols)}` · one shared starting equity: **$100**",
        "",
        f"**Verdict: {verdict}**",
        "",
        "## Frozen holdouts",
        "",
        f"- M5: {metric_line(hold_m5)}",
        f"- M1: {metric_line(hold_m1)}",
        "",
        "The M1 Yahoo sample is intrinsically short; its holdout cannot establish long-run reliability even if it is perfect.",
        "",
        "## Selected parameters",
        "",
        "```yaml",
        yaml.safe_dump(
            {
                "m5": {k: v for k, v in selected_m5.items() if k.startswith("cafb_")},
                "m1": {k: v for k, v in selected_m1.items() if k.startswith("cafb_")},
            },
            sort_keys=False,
        ).strip(),
        "```",
        "",
        "## Cost and sizing stress",
        "",
        "| TF | Test | Trades | Trades/day | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in stress:
        lines.append(
            f"| {r['timeframe']} | {r['segment']} | {r['trades']} | {r['trades_per_day']:.1f} | "
            f"{r['win_rate']:.1f}% | {r['expectancy_r']:+.3f} | {fmt_pf(r['profit_factor'])} | "
            f"{r['max_drawdown_pct']:.1f}% | ${r['end_equity']:.2f} | ${r['profit_per_day']:+.2f} | {r['halt_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Existing-algorithm benchmark — validation ranking",
            "",
            "All distinct registered functions, the two generic engines, and all 11 catalog strategies were attempted with the same shared-capital and 1.5x-cost assumptions.",
            "",
            "| Strategy | Trades | Trades/day | WR | Net E[R] | PF | DD | $100 end |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for r in valid_bench:
        lines.append(
            f"| `{r['strategy']}` | {r['trades']} | {r['trades_per_day']:.1f} | {r['win_rate']:.1f}% | "
            f"{r['expectancy_r']:+.3f} | {fmt_pf(r['profit_factor'])} | {r['max_drawdown_pct']:.1f}% | ${r['end_equity']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Data windows",
            "",
        ]
    )
    for tf, data in [("5m", data_m5), ("1m", data_m1)]:
        for symbol, df in data.items():
            lines.append(
                f"- {tf} `{symbol}`: {len(df)} bars, {df.time.iloc[0]} to {df.time.iloc[-1]}, "
                f"actual interval `{df.attrs.get('actual_interval', tf)}`."
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Profit/day is the historical net P&L divided by calendar span; it is not a promised daily payment.",
            "- Trades include round-trip spread, slippage and commission assumptions. Raw signals are not counted.",
            "- Same-bar SL/TP collisions are resolved stop-first and counted as ambiguous.",
            "- The basket enforces shared equity, simultaneous-position, heat, currency-exposure, leverage, minimum-unit and unit-step constraints.",
            "- Aggressive risk changes the loss path, not the strategy's underlying edge. A 100% short sample never licenses all-in live sizing.",
            "",
            f"Details: `{DETAILS}` and `{SEARCH}`",
            "",
        ]
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config_cafb_basket.yaml")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")
    args = parser.parse_args()
    cfg = base_config(args.config)
    symbols = list(cfg["symbols"])
    data_m5 = get_data(symbols, "5m", 59, args.refresh)
    data_m1 = get_data(symbols, "1m", 7, args.refresh)

    if args.skip_benchmark and DETAILS.exists():
        benchmark = pd.read_csv(DETAILS).to_dict("records")
    else:
        benchmark = benchmark_algorithms(data_m5, cfg)
        pd.DataFrame(benchmark).to_csv(DETAILS, index=False)
    selected_m5, search_m5 = tune_cafb(data_m5, cfg, "5m")
    selected_m1, search_m1 = tune_cafb(data_m1, cfg, "1m")
    pd.DataFrame(search_m5 + search_m1).to_csv(SEARCH, index=False)

    stress = final_stress(data_m5, selected_m5, "5m") + final_stress(data_m1, selected_m1, "1m")
    tuned_cfg = {k: v for k, v in selected_m1.items() if not k.startswith("_")}
    tuned_cfg.update({"timeframe": "1m", "lookback_days": 7, "test_name": "cafb_basket_tuned"})
    TUNED.write_text(yaml.safe_dump(tuned_cfg, sort_keys=False))
    write_report(symbols, data_m5, data_m1, benchmark, selected_m5, selected_m1, stress)
    print(f"REPORT {REPORT}")
    print(f"CONFIG {TUNED}")


if __name__ == "__main__":
    main()
