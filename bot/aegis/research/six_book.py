"""Six-book research stack: ensemble weak signals (Zuckerman) + confluence gates.

Books mapped (all research_proxy until PDFs extracted):
- Frost/Prechter: Elliott leg phase via elliott.py
- Gann: cycle/angle via gann.py
- Johnson: spread gate via johnson.py
- Chan: BB fade + momentum
- Prado: fractional diff feature + meta-label training path
- Zuckerman: require multiple independent votes before entry
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aegis.research.entry_features import add_entry_features
from aegis.research.elliott import add_elliott_legs
from aegis.research.gann import add_gann_columns
from aegis.research.johnson import add_johnson_columns, johnson_allows
from aegis.research.prado import add_prado_columns


def prepare_six_book(df: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    from aegis.strategy import prepare

    out = prepare(df, {**cfg, "signal_mode": "firehose"})
    out = add_entry_features(out)
    out = add_elliott_legs(out)
    out = add_gann_columns(out)
    out = add_johnson_columns(out, cfg)
    out = add_prado_columns(out)
    if "bb_upper" in out.columns and "bb_lower" in out.columns:
        width = (out["bb_upper"].astype(float) - out["bb_lower"].astype(float)).replace(0, np.nan)
        out["bb_pct_b"] = (
            (out["close"].astype(float) - out["bb_lower"].astype(float)) / width
        ).fillna(0.5)
    else:
        out["bb_pct_b"] = 0.5
    return out


def _htf_buy(row: pd.Series) -> bool:
    try:
        return float(row.get("h1_up") or 0.0) >= 0.5
    except (TypeError, ValueError):
        return False


def _htf_sell(row: pd.Series) -> bool:
    return not _htf_buy(row)


def stack_votes(row: pd.Series, side: str) -> int:
    """Count independent book-aligned votes for a direction (Zuckerman weak-signal stack)."""
    if not johnson_allows(row):
        return 0
    votes = 0
    event = str(row.get("struct_event") or "")
    try:
        phase = int(row.get("elliott_phase") or 0)
    except (TypeError, ValueError):
        phase = 0
    try:
        bb_b = float(row.get("bb_pct_b") or 0.5)
    except (TypeError, ValueError):
        bb_b = 0.5
    try:
        cep = float(row.get("close_ema_pips") or 0.0)
    except (TypeError, ValueError):
        cep = 0.0
    try:
        ret3 = float(row.get("ret3_pips") or 0.0)
    except (TypeError, ValueError):
        ret3 = 0.0
    try:
        fd = float(row.get("prado_fdiff") or 0.0)
    except (TypeError, ValueError):
        fd = 0.0
    gann_hit = float(row.get("gann_cycle_hit") or 0.0) >= 0.5

    if side == "buy":
        if event in {"failure_dn", "retest_up", "breakout_up"}:
            votes += 1
        if bb_b <= 0.05:
            votes += 1
        if cep > 0 and ret3 > 0:
            votes += 1
        if phase in {3, 5} and float(row.get("elliott_up_leg") or 0) >= 0.5:
            votes += 1
        if gann_hit and float(row.get("gann_angle_z") or 0) > 0:
            votes += 1
        if fd > 0 and _htf_buy(row):
            votes += 1
    else:
        if event in {"failure_up", "retest_dn", "breakout_dn"}:
            votes += 1
        if bb_b >= 0.95:
            votes += 1
        if cep < 0 and ret3 < 0:
            votes += 1
        if phase in {3, 5} and float(row.get("elliott_up_leg") or 0) < 0.5:
            votes += 1
        if gann_hit and float(row.get("gann_angle_z") or 0) < 0:
            votes += 1
        if fd < 0 and _htf_sell(row):
            votes += 1
    return votes
