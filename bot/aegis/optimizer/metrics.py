"""Trade-list metrics for snapshots and backtest wrappers. No invented stats."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np
import pandas as pd


def _pnls(trades: Iterable[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for row in trades:
        if "pnl" in row and row["pnl"] is not None:
            out.append(float(row["pnl"]))
        elif "profit" in row and row["profit"] is not None:
            out.append(float(row["profit"]))
    return out


def max_consecutive(flags: list[bool]) -> int:
    best = cur = 0
    for flag in flags:
        if flag:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def compute_trade_metrics(
    trades: list[dict[str, Any]],
    *,
    equity_samples: list[float] | None = None,
    starting_equity: float | None = None,
) -> dict[str, Any]:
    pnls = _pnls(trades)
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gp = float(sum(wins)) if wins else 0.0
    gl = float(-sum(losses)) if losses else 0.0
    wr = (100.0 * len(wins) / n) if n else 0.0
    pf = (gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0)
    avg_win = float(sum(wins) / len(wins)) if wins else 0.0
    avg_loss = float(sum(losses) / len(losses)) if losses else 0.0
    expectancy = float(sum(pnls) / n) if n else 0.0
    consec_w = max_consecutive([p > 0 for p in pnls])
    consec_l = max_consecutive([p <= 0 for p in pnls])
    max_dd = 0.0
    samples = list(equity_samples or [])
    if not samples and starting_equity is not None:
        eq = float(starting_equity)
        samples = [eq]
        for p in pnls:
            eq += p
            samples.append(eq)
    if len(samples) >= 2:
        peak = samples[0]
        for v in samples:
            peak = max(peak, v)
            if peak > 0:
                max_dd = max(max_dd, (peak - v) / peak * 100.0)
    return {
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": wr,
        "profit_factor": pf if math.isfinite(pf) else None,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": expectancy,
        "net_pnl": float(sum(pnls)) if pnls else 0.0,
        "max_drawdown_pct": max_dd,
        "max_consecutive_wins": consec_w,
        "max_consecutive_losses": consec_l,
        "equity_samples": len(samples),
    }


def equity_ratios(curve: pd.Series) -> dict[str, float | None]:
    """Bar-level Sharpe/Sortino from pct_change. Not annualized."""
    if curve is None or len(curve) <= 2:
        return {"sharpe": None, "sortino": None}
    rets = curve.astype(float).pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if len(rets) < 2:
        return {"sharpe": None, "sortino": None}
    mean = float(rets.mean())
    std = float(rets.std(ddof=1))
    down = rets[rets < 0]
    dstd = float(down.std(ddof=1)) if len(down) > 1 else 0.0
    scale = math.sqrt(len(rets))
    sharpe = (mean / std * scale) if std > 1e-12 else None
    sortino = (mean / dstd * scale) if dstd > 1e-12 else None
    return {"sharpe": sharpe, "sortino": sortino}


def extras_from_trades_df(trades: pd.DataFrame) -> dict[str, Any]:
    if trades is None or trades.empty or "pnl" not in trades.columns:
        return {
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_consecutive_losses": 0,
            "max_consecutive_wins": 0,
        }
    pnls = [float(x) for x in trades["pnl"].tolist()]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    return {
        "avg_win": float(sum(wins) / len(wins)) if wins else 0.0,
        "avg_loss": float(sum(losses) / len(losses)) if losses else 0.0,
        "max_consecutive_wins": max_consecutive([p > 0 for p in pnls]),
        "max_consecutive_losses": max_consecutive([p <= 0 for p in pnls]),
    }


def utc_hour_now() -> int:
    return datetime.now(timezone.utc).hour
