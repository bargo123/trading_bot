#!/usr/bin/env python3
"""Tune the higher-frequency EMA/ATR pulse family on frozen splits."""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aegis.basket_backtest import run_basket_backtest
from aegis.pulse import prepare_pulse, sig_pulse
from tune_cafb_basket import base_config, fmt_pf, get_data, metric_line, metrics, split_frames

REPORT = ROOT / "reports" / "PULSE_BASKET.md"
SEARCH = ROOT / "reports" / "pulse_search_results.csv"
TUNED = ROOT / "config_pulse_basket.tuned.yaml"


def stable_score(dev: dict[str, Any], val: dict[str, Any], min_dev: int, min_val: int) -> float:
    if dev["trades"] < min_dev or val["trades"] < min_val:
        return -1e9
    dev_pf = float(dev["profit_factor"])
    val_pf = float(val["profit_factor"])
    dev_pf_cap = 5.0 if not math.isfinite(dev_pf) else min(dev_pf, 5.0)
    val_pf_cap = 5.0 if not math.isfinite(val_pf) else min(val_pf, 5.0)
    stable = dev["expectancy_r"] > 0 and val["expectancy_r"] > 0 and dev_pf > 1 and val_pf > 1
    perfect = dev["win_rate"] >= 99.999 and val["win_rate"] >= 99.999
    return (
        (1000.0 if perfect else 0.0)
        + (100.0 if stable else -100.0)
        + 100.0 * min(dev["expectancy_r"], val["expectancy_r"])
        + 5.0 * min(dev_pf_cap, val_pf_cap)
        + 0.05 * min(dev["win_rate"], val["win_rate"])
        + 0.15 * min(dev["trades_per_day"], val["trades_per_day"], 100.0)
        - 0.25 * max(dev["max_drawdown_pct"], val["max_drawdown_pct"])
    )


def tune(raw: dict[str, pd.DataFrame], cfg: dict[str, Any], timeframe: str):
    context = 5 if timeframe == "1m" else 15
    min_dev = 20 if timeframe == "1m" else 40
    min_val = 8 if timeframe == "1m" else 15
    rows = []
    best = None
    for adx_min in [12, 20]:
        feature_cfg = {
            **cfg,
            "signal_mode": "pulse_scalp",
            "algo": "pulse_scalp",
            "cafb_context_minutes": context,
            "cafb_htf_adx_min": adx_min,
        }
        prepared = {s: prepare_pulse(df, feature_cfg) for s, df in raw.items()}
        dev = split_frames(prepared, "development")
        val = split_frames(prepared, "validation")
        if timeframe == "1m":
            distance_grid = [(sl, tp, "pips") for sl, tp in itertools.product([10.0, 20.0, 40.0], [3.0, 5.0, 8.0])]
        else:
            distance_grid = [(sl, tp, "atr") for sl, tp in itertools.product([2.0, 5.0, 10.0], [0.75, 1.0, 1.5])]
        for (regime_mode, z_atr, rsi_edge), (sl_value, tp_value, distance_mode) in itertools.product(
            itertools.product(
            ["range", "trend", "both"],
            [0.25, 0.75],
            [40, 45],
            ),
            distance_grid,
        ):
            c = {
                **feature_cfg,
                "pulse_regime_mode": regime_mode,
                "pulse_z_atr": z_atr,
                "pulse_rsi_edge": rsi_edge,
                "pulse_sl_atr": sl_value if distance_mode == "atr" else None,
                "pulse_tp_atr": tp_value if distance_mode == "atr" else None,
                "pulse_sl_pips": sl_value if distance_mode == "pips" else None,
                "pulse_tp_pips": tp_value if distance_mode == "pips" else None,
                "pulse_pip_size": 0.0001,
            }
            dev_res = run_basket_backtest(dev, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_pulse)
            val_res = run_basket_backtest(val, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_pulse)
            dev_m = metrics("pulse_scalp", "development", dev, dev_res, c)
            val_m = metrics("pulse_scalp", "validation", val, val_res, c)
            score = stable_score(dev_m, val_m, min_dev, min_val)
            row = {
                "timeframe": timeframe,
                "adx_min": adx_min,
                "regime_mode": regime_mode,
                "z_atr": z_atr,
                "rsi_edge": rsi_edge,
                "distance_mode": distance_mode,
                "sl_value": sl_value,
                "tp_value": tp_value,
                "score": score,
                **{f"dev_{k}": v for k, v in dev_m.items() if k not in {"strategy", "segment"}},
                **{f"val_{k}": v for k, v in val_m.items() if k not in {"strategy", "segment"}},
            }
            rows.append(row)
            if best is None or score > best[0]:
                best = (score, c, prepared, dev_m, val_m)
    assert best is not None
    score, selected, prepared, dev_m, val_m = best
    hold = split_frames(prepared, "holdout")
    hold_res = run_basket_backtest(hold, selected, prepare_fn=lambda df, _cfg: df, signal_fn=sig_pulse)
    hold_m = metrics("pulse_scalp", "holdout", hold, hold_res, selected)
    selected = {
        **selected,
        "_selection_score": score,
        "_development": dev_m,
        "_validation": val_m,
        "_holdout": hold_m,
    }
    print(
        f"PULSE {timeframe} HOLDOUT n={hold_m['trades']} WR={hold_m['win_rate']:.2f}% "
        f"E[R]={hold_m['expectancy_r']:+.3f} PF={hold_m['profit_factor']:.2f} "
        f"DD={hold_m['max_drawdown_pct']:.2f}% eq={hold_m['end_equity']:.2f}",
        flush=True,
    )
    return selected, rows


def stress(raw: dict[str, pd.DataFrame], selected: dict[str, Any], timeframe: str):
    cfg = {k: v for k, v in selected.items() if not k.startswith("_")}
    prepared = {s: prepare_pulse(df, cfg) for s, df in raw.items()}
    hold = split_frames(prepared, "holdout")
    rows = []
    for scale in [1.0, 1.5, 2.0]:
        c = {
            **cfg,
            "spread_bps": 0.4 * scale,
            "slippage_bps": 0.2 * scale,
            "cost_buffer": scale,
            "risk_percent": 2.0,
        }
        res = run_basket_backtest(hold, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_pulse)
        m = metrics("pulse_scalp", f"holdout_cost_{scale:.1f}x", hold, res, c)
        m.update({"timeframe": timeframe, "cost_scale": scale, "risk_percent": 2.0})
        rows.append(m)
    for rp in [1.0, 2.0, 5.0, 10.0, 20.0]:
        c = {
            **cfg,
            "spread_bps": 0.6,
            "slippage_bps": 0.3,
            "cost_buffer": 1.5,
            "risk_percent": rp,
            "hr_risk_max_cap": rp,
            "max_portfolio_heat_percent": 2 * rp,
            "max_daily_loss_percent": max(8.0, 2 * rp),
            "max_total_drawdown_percent": max(30.0, 2 * rp),
        }
        res = run_basket_backtest(hold, c, prepare_fn=lambda df, _cfg: df, signal_fn=sig_pulse)
        m = metrics("pulse_scalp", f"holdout_risk_{rp:.0f}", hold, res, c)
        m.update({"timeframe": timeframe, "cost_scale": 1.5, "risk_percent": rp})
        rows.append(m)
    return rows


def write_report(symbols, data_m5, data_m1, selected_m5, selected_m1, stresses):
    h5, h1 = selected_m5["_holdout"], selected_m1["_holdout"]
    perfect = [m for m in [h5, h1] if m["trades"] > 0 and m["win_rate"] >= 99.999]
    if perfect:
        verdict = "At least one exact frozen holdout was 100% WR; its sample size and confidence interval below limit the claim."
    else:
        verdict = "No EMA/ATR pulse candidate achieved 100% WR on frozen holdout after costs."
    lines = [
        "# EMA/ATR Pulse Basket — measured results",
        "",
        f"Symbols: `{', '.join(symbols)}` · one shared starting equity: **$100**",
        "",
        f"**Verdict: {verdict}**",
        "",
        "## Selected development, validation, and frozen holdout",
        "",
    ]
    for tf, sel in [("M5", selected_m5), ("M1", selected_m1)]:
        lines.extend(
            [
                f"### {tf}",
                "",
                f"- Development: {metric_line(sel['_development'])}",
                f"- Validation: {metric_line(sel['_validation'])}",
                f"- Frozen holdout: {metric_line(sel['_holdout'])}",
                "",
            ]
        )
    lines.extend(
        [
            "## Selected parameters",
            "",
            "```yaml",
            yaml.safe_dump(
                {
                    "m5": {k: v for k, v in selected_m5.items() if k.startswith("pulse_") or k == "cafb_htf_adx_min"},
                    "m1": {k: v for k, v in selected_m1.items() if k.startswith("pulse_") or k == "cafb_htf_adx_min"},
                },
                sort_keys=False,
            ).strip(),
            "```",
            "",
            "## Holdout cost and risk stress",
            "",
            "| TF | Test | Trades | Trades/day | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for r in stresses:
        lines.append(
            f"| {r['timeframe']} | {r['segment']} | {r['trades']} | {r['trades_per_day']:.1f} | "
            f"{r['win_rate']:.1f}% | {r['expectancy_r']:+.3f} | {fmt_pf(r['profit_factor'])} | "
            f"{r['max_drawdown_pct']:.1f}% | ${r['end_equity']:.2f} | ${r['profit_per_day']:+.2f} | {r['halt_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Audit interpretation",
            "",
            "- Selection used development and validation only. Each selected configuration opened its holdout once.",
            "- Costs are charged round trip; raw signals are not trades; SL/TP collisions are stop-first and counted.",
            "- Minimum units, unit step, leverage, shared heat, currency exposure and simultaneous-position limits are enforced.",
            "- Profit/day is historical P&L divided by calendar span, not a promised income rate.",
            "- Compare the failed-break and complete legacy benchmark in `reports/CAFB_BASKET.md`.",
            "",
            f"Full grid: `{SEARCH}`",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "config_pulse_basket.yaml")
    args = parser.parse_args()
    cfg = base_config(args.config)
    symbols = list(cfg["symbols"])
    data_m5 = get_data(symbols, "5m", 59, False)
    data_m1 = get_data(symbols, "1m", 7, False)
    selected_m5, rows_m5 = tune(data_m5, cfg, "5m")
    selected_m1, rows_m1 = tune(data_m1, cfg, "1m")
    pd.DataFrame(rows_m5 + rows_m1).to_csv(SEARCH, index=False)
    stresses = stress(data_m5, selected_m5, "5m") + stress(data_m1, selected_m1, "1m")
    tuned = {k: v for k, v in selected_m1.items() if not k.startswith("_")}
    tuned.update({"timeframe": "1m", "lookback_days": 7, "test_name": "pulse_basket_tuned"})
    TUNED.write_text(yaml.safe_dump(tuned, sort_keys=False))
    write_report(symbols, data_m5, data_m1, selected_m5, selected_m1, stresses)
    print(f"REPORT {REPORT}")
    print(f"CONFIG {TUNED}")


if __name__ == "__main__":
    main()
