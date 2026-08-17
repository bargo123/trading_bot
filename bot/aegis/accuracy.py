"""Jansen factor score + Harris jump censor.

Jansen *Hands-On ML for Algorithmic Trading* (2018): alpha factors from lagged
returns / RSI / efficiency; trade only when the score agrees with the side.
No future bars. Not a trained GBDT and not a 100% WR claim.

Harris *Trading and Exchanges* (2002): market orders pay the spread; after an
informed jump, the next take is adversely selected — do not chase that bar.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


def _flag(row: pd.Series, key: str) -> bool:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return False
    except (TypeError, ValueError):
        return False
    return bool(val)


def _num(row: pd.Series, key: str) -> float | None:
    val = row.get(key)
    try:
        if val is None or pd.isna(val):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def accuracy_allows(row: pd.Series, cfg: dict[str, Any], side: str) -> bool:
    """True when enabled Jansen/Harris gates allow this firehose side."""
    side = str(side or "").lower()
    if bool(cfg.get("firehose_jansen_filter", False)):
        score = _num(row, "jansen_score")
        if score is None:
            return False
        thresh = float(cfg.get("jansen_score_min", 0.15) or 0.0)
        if side == "buy" and score < thresh:
            return False
        if side == "sell" and score > -thresh:
            return False
    if bool(cfg.get("firehose_harris_jump", False)) and _flag(row, "harris_jump"):
        o = _num(row, "open")
        c = _num(row, "close")
        if o is not None and c is not None:
            if side == "buy" and c > o:
                return False
            if side == "sell" and c < o:
                return False
    return True
