"""Wrap existing run_backtest with chronological IS/OOS and optional walk-forward."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from aegis.backtest import BacktestResult, run_backtest
from aegis.optimizer.metrics import equity_ratios, extras_from_trades_df


def synthetic_ohlcv(n: int = 800, start: float = 1.10, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC")
    rets = rng.normal(0.00002, 0.00018, n)
    close = start * np.exp(np.cumsum(rets))
    high = close * (1.0 + np.abs(rng.normal(0, 0.00012, n)))
    low = close * (1.0 - np.abs(rng.normal(0, 0.00012, n)))
    open_ = np.roll(close, 1)
    open_[0] = start
    return pd.DataFrame(
        {
            "time": t,
            "open": open_,
            "high": np.maximum(high, np.maximum(open_, close)),
            "low": np.minimum(low, np.minimum(open_, close)),
            "close": close,
            "volume": rng.integers(50, 200, n),
        }
    )


def chronological_split(df: pd.DataFrame, is_fraction: float = 0.7) -> tuple[pd.DataFrame, pd.DataFrame]:
    n = len(df)
    cut = max(1, min(n - 1, int(n * float(is_fraction))))
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def walk_forward_slices(n: int, folds: int = 3) -> list[tuple[slice, slice]]:
    """Anchored walk-forward: expanding IS, next chunk OOS."""
    if n < 40 or folds < 2:
        return []
    chunk = n // (folds + 1)
    if chunk < 10:
        return []
    out: list[tuple[slice, slice]] = []
    for i in range(folds):
        is_end = chunk * (i + 1)
        oos_end = chunk * (i + 2) if i < folds - 1 else n
        if oos_end <= is_end:
            continue
        out.append((slice(0, is_end), slice(is_end, oos_end)))
    return out


def summarize_result(res: BacktestResult) -> dict[str, Any]:
    extras = extras_from_trades_df(res.trades)
    ratios = equity_ratios(res.equity_curve)
    pf = res.profit_factor
    return {
        "win_rate": float(res.win_rate),
        "profit_factor": None if not math.isfinite(pf) else float(pf),
        "max_drawdown_pct": float(res.max_drawdown_pct),
        "expectancy_r": float(res.expectancy_r),
        "total_trades": int(res.total_trades),
        "net_pnl": float(res.net_pnl),
        "final_equity": float(res.final_equity),
        "halt_reason": res.halt_reason,
        **extras,
        **ratios,
    }


def run_split_backtest(df: pd.DataFrame, cfg: dict[str, Any], *, is_fraction: float = 0.7) -> dict[str, Any]:
    is_df, oos_df = chronological_split(df, is_fraction)
    is_res = run_backtest(is_df, cfg)
    oos_res = run_backtest(oos_df, cfg, intel_memory=is_res.intel_memory)
    return {
        "is": summarize_result(is_res),
        "oos": summarize_result(oos_res),
        "is_bars": len(is_df),
        "oos_bars": len(oos_df),
    }


def run_walk_forward(df: pd.DataFrame, cfg: dict[str, Any], *, folds: int = 3) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, (is_sl, oos_sl) in enumerate(walk_forward_slices(len(df), folds), start=1):
        is_res = run_backtest(df.iloc[is_sl], cfg)
        oos_res = run_backtest(df.iloc[oos_sl], cfg, intel_memory=is_res.intel_memory)
        rows.append(
            {
                "fold": i,
                "is": summarize_result(is_res),
                "oos": summarize_result(oos_res),
            }
        )
    return rows


def accept_gate(
    baseline_oos: dict[str, Any],
    candidate_oos: dict[str, Any],
    *,
    min_trades: int = 20,
    dd_tolerance_pct: float = 2.0,
    stored_best_e: float | None = None,
) -> tuple[bool, str]:
    """Tharp-safe: OOS expectancy must improve vs this-run baseline and stored best."""
    cand_n = int(candidate_oos.get("total_trades") or 0)
    if cand_n < int(min_trades):
        return False, f"OOS trades {cand_n} < min_trades {min_trades}"
    base_e = float(baseline_oos.get("expectancy_r") or 0.0)
    cand_e = float(candidate_oos.get("expectancy_r") or 0.0)
    if cand_e <= base_e:
        return False, f"OOS expectancy_r {cand_e:.4f} <= baseline {base_e:.4f}"
    base_dd = float(baseline_oos.get("max_drawdown_pct") or 0.0)
    cand_dd = float(candidate_oos.get("max_drawdown_pct") or 0.0)
    if cand_dd > base_dd + float(dd_tolerance_pct):
        return False, (
            f"OOS max DD {cand_dd:.2f}% worse than baseline {base_dd:.2f}% "
            f"+ tolerance {dd_tolerance_pct}"
        )
    base_wr = float(baseline_oos.get("win_rate") or 0.0)
    cand_wr = float(candidate_oos.get("win_rate") or 0.0)
    if cand_wr > base_wr and cand_e < base_e:
        return False, "WR up / expectancy down (Tharp) — reject"
    if stored_best_e is not None and cand_e <= float(stored_best_e) + 1e-12:
        return False, (
            f"OOS expectancy_r {cand_e:.4f} <= stored best {float(stored_best_e):.4f}"
        )
    return True, "OOS expectancy improved without a disallowed DD or Tharp WR/E inversion"
