"""Objective swing-leg proxy for Elliott research. Not subjective wave labeling.

Aronson rejects hand-drawn Elliott as untestable. This module only counts alternating
confirmed pivots — a research_proxy, not Frost & Prechter wave theory.
"""
from __future__ import annotations

import pandas as pd

from aegis.research.entry_features import add_structure_columns


def add_elliott_legs(df: pd.DataFrame) -> pd.DataFrame:
    """Alternating swing-leg count on confirmed pivots (1–5 cycle proxy)."""
    out = add_structure_columns(df)
    high = out["high"].astype(float)
    low = out["low"].astype(float)

    is_swing_high = (high > high.shift(1)) & (high >= high.shift(-1))
    is_swing_low = (low < low.shift(1)) & (low <= low.shift(-1))
    confirmed_high = is_swing_high.shift(1).fillna(False)
    confirmed_low = is_swing_low.shift(1).fillna(False)

    leg = pd.Series(0, index=out.index, dtype=int)
    up_leg = pd.Series(0.0, index=out.index, dtype=float)
    direction = 0  # 1 = last swing was high, -1 = low
    count = 0
    for i in range(len(out)):
        if bool(confirmed_high.iloc[i]):
            if direction == -1:
                count += 1
            elif direction == 0:
                count = 1
            direction = 1
        elif bool(confirmed_low.iloc[i]):
            if direction == 1:
                count += 1
            elif direction == 0:
                count = 1
            direction = -1
        leg.iloc[i] = count
        up_leg.iloc[i] = 1.0 if direction == 1 else 0.0
    out["elliott_leg"] = leg
    out["elliott_phase"] = ((leg - 1) % 5) + 1
    out["elliott_up_leg"] = up_leg
    return out
