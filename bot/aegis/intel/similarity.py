"""Historical similarity on pre-entry features. Past trades only.

INVENTED_ALGORITHM: k-nearest CORE signals by z-scored ER / RSI / range_loc /
jansen_score. If neighbor win-rate < threshold, REJECT. No future trades.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


KEYS = ("kaufman_er", "rsi", "range_loc", "jansen_score", "adx")


def feature_vec(row: pd.Series | dict[str, Any]) -> np.ndarray:
    vals = []
    getter = row.get if hasattr(row, "get") else lambda k, d=None: row[k] if k in row else d
    for key in KEYS:
        try:
            v = getter(key)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                vals.append(0.0)
            else:
                vals.append(float(v))
        except (TypeError, ValueError, KeyError):
            vals.append(0.0)
    return np.asarray(vals, dtype=float)


def neighbor_win_rate(
    query: pd.Series | dict[str, Any],
    memory: list[dict[str, Any]],
    *,
    k: int = 15,
) -> float | None:
    """Win rate of k nearest *past* labeled rows. None if memory too small."""
    if len(memory) < max(5, k // 2):
        return None
    q = feature_vec(query if not isinstance(query, dict) else pd.Series(query))
    xs = []
    ys = []
    for rec in memory:
        feats = rec.get("features") or rec
        xs.append(feature_vec(feats if isinstance(feats, dict) else rec))
        ys.append(1.0 if rec.get("win") else 0.0)
    mat = np.vstack(xs)
    scale = mat.std(axis=0)
    scale = np.where(scale < 1e-9, 1.0, scale)
    dist = np.sqrt((((mat - q) / scale) ** 2).sum(axis=1))
    k_use = min(int(k), len(dist))
    idx = np.argpartition(dist, k_use - 1)[:k_use]
    return float(np.mean([ys[i] for i in idx]))


def similarity_allows(
    row: pd.Series,
    memory: list[dict[str, Any]],
    *,
    k: int = 15,
    min_wr: float = 0.45,
) -> bool:
    wr = neighbor_win_rate(row, memory, k=k)
    if wr is None:
        return True
    return wr >= float(min_wr)
