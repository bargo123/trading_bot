#!/usr/bin/env python3
"""Re-measure the selected 1h 100%-WR config after audit accounting fixes."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.backtest import run_backtest
from aegis.data import fetch_ohlcv

REPORT = ROOT / "reports" / "TUNED_100WR_CORRECTED.md"
CACHE = ROOT / "data" / "cafb_snapshots" / "EURUSD_X_1h_90d.csv"


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = wins / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return 100 * max(0.0, center - half), 100 * min(1.0, center + half)


def load_data(refresh: bool = False) -> pd.DataFrame:
    if CACHE.exists() and not refresh:
        df = pd.read_csv(CACHE, parse_dates=["time"])
        df["time"] = pd.to_datetime(df["time"], utc=True)
        return df
    df = fetch_ohlcv("EURUSD=X", "1h", 90)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CACHE, index=False)
    return df


def result_row(label: str, df: pd.DataFrame, cfg: dict) -> dict:
    res = run_backtest(df, cfg)
    start = pd.Timestamp(df.time.iloc[0])
    end = pd.Timestamp(df.time.iloc[-1])
    span = max((end - start).total_seconds() / 86400, 1 / 24)
    wins = int((res.trades.pnl > 0).sum()) if res.total_trades else 0
    lo, hi = wilson(wins, res.total_trades)
    return {
        "label": label,
        "start_utc": str(start),
        "end_utc": str(end),
        "trades": res.total_trades,
        "trades_per_day": res.total_trades / span,
        "win_rate": res.win_rate,
        "ci_low": lo,
        "ci_high": hi,
        "expectancy_r": res.expectancy_r,
        "profit_factor": res.profit_factor,
        "max_drawdown_pct": res.max_drawdown_pct,
        "start_equity": float(cfg["starting_equity"]),
        "end_equity": res.final_equity,
        "net_pnl": res.net_pnl,
        "profit_per_day": res.net_pnl / span,
        "halt_reason": res.halt_reason or "none",
        "ambiguous": res.ambiguous_exits,
    }


def fmt_pf(value: float) -> str:
    return "inf" if not math.isfinite(value) else f"{value:.2f}"


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config_tuned_100wr.yaml").read_text())
    data = load_data(refresh=True)
    end = pd.Timestamp(data.time.iloc[-1])
    windows = []
    for days in [45, 60, 75, 90]:
        sample = data[data.time >= end - pd.Timedelta(days=days)].copy().reset_index(drop=True)
        windows.append(result_row(f"{days}d_all_in", sample, cfg))
    sample60 = data[data.time >= end - pd.Timedelta(days=60)].copy().reset_index(drop=True)
    risk_rows = []
    for rp in [1, 2, 5, 10, 20, 100]:
        c = {
            **cfg,
            "risk_percent": rp,
            "hr_risk_max_cap": rp,
            "max_daily_loss_percent": 100,
            "max_total_drawdown_percent": 100,
        }
        risk_rows.append(result_row(f"risk_{rp}", sample60, c))
    cost_rows = []
    for scale in [1.0, 1.5, 2.0]:
        c = {
            **cfg,
            "spread_bps": float(cfg["spread_bps"]) * scale,
            "slippage_bps": float(cfg["slippage_bps"]) * scale,
            "cost_buffer": float(cfg.get("cost_buffer", 1.0)) * scale,
        }
        cost_rows.append(result_row(f"cost_{scale:.1f}x", sample60, c))

    lines = [
        "# Corrected re-measurement — tuned 1h 100%-WR configuration",
        "",
        "The original selected parameters were not re-tuned. This rerun uses cost-adjusted R, end-of-test liquidation, and historical-time risk checks.",
        "",
        "## Window results",
        "",
        "| Window | Exact UTC sample | Trades | Trades/day | WR (95% Wilson CI) | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in windows:
        lines.append(
            f"| {r['label']} | {r['start_utc']} → {r['end_utc']} | {r['trades']} | {r['trades_per_day']:.2f} | "
            f"{r['win_rate']:.1f}% ({r['ci_low']:.1f}–{r['ci_high']:.1f}%) | {r['expectancy_r']:+.3f} | "
            f"{fmt_pf(r['profit_factor'])} | {r['max_drawdown_pct']:.1f}% | ${r['end_equity']:.2f} | "
            f"${r['profit_per_day']:+.2f} | {r['halt_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Same 60-day signals — sizing comparison",
            "",
            "| Risk/trade | Trades | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for r in risk_rows:
        rp = r["label"].split("_")[1]
        lines.append(
            f"| {rp}% | {r['trades']} | {r['win_rate']:.1f}% | {r['expectancy_r']:+.3f} | {fmt_pf(r['profit_factor'])} | "
            f"{r['max_drawdown_pct']:.1f}% | ${r['end_equity']:.2f} | ${r['profit_per_day']:+.2f} | {r['halt_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Same 60-day signals — cost stress at 100% risk",
            "",
            "| Cost | Trades | WR | Net E[R] | PF | Max DD | $100 end | Profit/day | Halt |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for r in cost_rows:
        lines.append(
            f"| {r['label'].replace('cost_', '')} | {r['trades']} | {r['win_rate']:.1f}% | {r['expectancy_r']:+.3f} | "
            f"{fmt_pf(r['profit_factor'])} | {r['max_drawdown_pct']:.1f}% | ${r['end_equity']:.2f} | "
            f"${r['profit_per_day']:+.2f} | {r['halt_reason']} |"
        )
    lines.extend(
        [
            "",
            "## Limits",
            "",
            "- This remains a previously selected parameter set on a rolling Yahoo sample, not a new frozen OOS discovery.",
            "- The single-symbol engine does not enforce broker lot size, leverage or margin, so the all-in row is not an executable $100 recommendation.",
            "- A perfect observed sample has a wide true-win-rate confidence interval and does not imply the next trade must win.",
            "",
            "```json",
            json.dumps({"windows": windows, "risk": risk_rows, "cost": cost_rows}, indent=2),
            "```",
            "",
        ]
    )
    REPORT.write_text("\n".join(lines))
    print(f"REPORT {REPORT}")


if __name__ == "__main__":
    main()

