"""Completed-bar pivots, support/resistance, breakout, failure, retest. No hindsight pivots."""
from __future__ import annotations

from typing import Any

import pandas as pd


def confirmed_pivots(df: pd.DataFrame, *, left: int = 1, right: int = 1) -> list[dict[str, Any]]:
    """A pivot at bar i is known only after bar i+right has closed."""
    if len(df) < left + right + 1:
        return []
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    last = len(df) - 1
    out: list[dict[str, Any]] = []
    for i in range(left, last - right + 1):
        decided = i + right
        if decided > last:
            continue
        window_h = high.iloc[i - left : i + right + 1]
        window_l = low.iloc[i - left : i + right + 1]
        if float(high.iloc[i]) >= float(window_h.max()) and float(high.iloc[i]) > float(high.iloc[i - 1]):
            out.append({"kind": "high", "bar_index": i, "decided_at": decided, "price": float(high.iloc[i])})
        if float(low.iloc[i]) <= float(window_l.min()) and float(low.iloc[i]) < float(low.iloc[i - 1]):
            out.append({"kind": "low", "bar_index": i, "decided_at": decided, "price": float(low.iloc[i])})
    return out


def structure_event(df: pd.DataFrame) -> dict[str, Any]:
    pivots = confirmed_pivots(df)
    last_close = float(df["close"].iloc[-1])
    highs = [p for p in pivots if p["kind"] == "high"]
    lows = [p for p in pivots if p["kind"] == "low"]
    resistance = max((p["price"] for p in highs), default=None)
    support = min((p["price"] for p in lows), default=None)
    kind = "none"
    if resistance is not None and last_close > resistance:
        kind = "breakout"
        if len(df) >= 2 and float(df["high"].iloc[-2]) > resistance and last_close < resistance:
            kind = "failure"
    elif support is not None and last_close < support:
        kind = "breakout"
        if len(df) >= 2 and float(df["low"].iloc[-2]) < support and last_close > support:
            kind = "failure"
    elif resistance is not None and abs(last_close - resistance) / max(resistance, 1e-9) < 0.0003:
        kind = "retest"
    elif support is not None and abs(last_close - support) / max(support, 1e-9) < 0.0003:
        kind = "retest"
    return {
        "kind": kind,
        "lookahead": False,
        "support": support,
        "resistance": resistance,
        "n_pivots": len(pivots),
        "label": "research_proxy",
    }
