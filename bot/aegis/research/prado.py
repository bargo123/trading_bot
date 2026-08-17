"""López de Prado AFML helpers. research_proxy — not the full AFML library.

Purged holdout lives in evaluate.py. Here: fractional-diff feature and meta-label target.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def fractional_diff(series: pd.Series, *, d: float = 0.4, thresh: float = 1e-4) -> pd.Series:
    """Fixed-weight fractional differentiation (simplified AFML Ch.5 proxy)."""
    x = series.astype(float)
    w = [1.0]
    k = 1
    while k < 64:
        w_k = -w[-1] * (d - k + 1) / k
        if abs(w_k) < thresh:
            break
        w.append(w_k)
        k += 1
    w_arr = np.array(w[::-1], dtype=float)
    vals = x.to_numpy()
    out = np.full(len(vals), np.nan, dtype=float)
    for i in range(len(w_arr) - 1, len(vals)):
        out[i] = float(np.dot(w_arr, vals[i - len(w_arr) + 1 : i + 1]))
    return pd.Series(out, index=x.index, dtype=float)


def add_prado_columns(df: pd.DataFrame, *, d: float = 0.4) -> pd.DataFrame:
    out = df.copy()
    fd = fractional_diff(out["close"], d=d)
    out["prado_fdiff"] = fd.reindex(out.index).fillna(0.0)
    return out


def meta_label_target(pnls: Sequence[float], *, min_ret: float = 0.0) -> np.ndarray:
    """1 when the primary trade was profitable after costs; 0 otherwise (AFML meta-label)."""
    arr = np.asarray(list(pnls), dtype=float)
    return (arr > float(min_ret)).astype(float)


def triple_barrier_label(
    close: pd.Series,
    *,
    pt: float,
    sl: float,
    max_bars: int,
) -> float:
    """Label the first bar of `close` by the first barrier touched: +1 pt, -1 sl, 0 vertical.

    `close` must be the path starting at the decision bar. Future prices are the
    outcome, not a feature — do not put this label into the feature matrix.
    """
    path = close.astype(float).to_numpy()
    if path.size == 0:
        return 0.0
    start = float(path[0])
    if start <= 0:
        return 0.0
    upper = start * (1.0 + float(pt))
    lower = start * (1.0 - float(sl))
    horizon = min(int(max_bars), path.size - 1)
    for i in range(1, horizon + 1):
        px = float(path[i])
        hit_up = px >= upper
        hit_dn = px <= lower
        if hit_up and hit_dn:
            return 0.0
        if hit_up:
            return 1.0
        if hit_dn:
            return -1.0
    return 0.0
