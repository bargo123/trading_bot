"""Johnson DMA lessons as research_proxy gates. No exchange DMA on retail MT5.

Johnson: liquidity, spread, and latency dominate short-horizon edge. We gate on spread
vs ATR using configured or assumed spread — not true order-book queue position.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def add_johnson_columns(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    spread = float(cfg.get("assumed_spread", cfg.get("spread", 0.00002)) or 0.00002)
    if "spread" in out.columns:
        spread_s = out["spread"].astype(float)
        spread_use = spread_s.where(spread_s > 0, other=spread)
    else:
        spread_use = spread
    if "atr" in out.columns:
        atr = out["atr"].astype(float).clip(lower=1e-9)
    else:
        atr = (out["high"].astype(float) - out["low"].astype(float)).clip(lower=1e-9)
    max_ratio = float(cfg.get("johnson_max_spread_atr", 0.12) or 0.12)
    if isinstance(spread_use, pd.Series):
        ratio = spread_use / atr
    else:
        ratio = spread / atr
    out["johnson_spread_ok"] = (ratio <= max_ratio).astype(float)
    return out


def johnson_allows(row: pd.Series) -> bool:
    try:
        return float(row.get("johnson_spread_ok") or 0.0) >= 0.5
    except (TypeError, ValueError):
        return False
