"""Gann time/price proxies. research_proxy until the 1976 extract is on disk.

Hand-drawn Gann angles are not coded here. Only objective bar-count cycles and a
slope-vs-ATR ratio that approximates 'price per unit time' without subjective anchors.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Common Gann bar counts cited in commodity timing chapters (research_proxy).
GANN_CYCLES = (45, 90, 144)


def add_gann_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    idx = np.arange(len(out), dtype=float)
    hit = np.zeros(len(out), dtype=float)
    for cycle in GANN_CYCLES:
        mod = idx % float(cycle)
        near = (mod <= 2.0) | (mod >= float(cycle) - 2.0)
        hit = np.maximum(hit, near.astype(float))
    out["gann_cycle_hit"] = hit

    close = out["close"].astype(float)
    look = 45
    slope = (close - close.shift(look)) / float(look)
    if "atr" in out.columns:
        atr = out["atr"].astype(float).clip(lower=1e-9)
    else:
        atr = (out["high"].astype(float) - out["low"].astype(float)).clip(lower=1e-9)
    out["gann_angle_z"] = (slope / atr).fillna(0.0)
    return out
