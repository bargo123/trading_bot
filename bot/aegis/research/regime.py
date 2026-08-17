"""Multi-timeframe regime from completed resampled bars. Not an M1 EMA alias."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aegis.research.mtf import mtf_state


def classify_regime(m1: pd.DataFrame) -> dict[str, Any]:
    state = mtf_state(m1)
    used = [tf for tf in ("M5", "M15", "H1", "H4") if (state.get(tf) or {}).get("complete")]
    h1 = (state.get("H1") or {})
    m5 = (state.get("M5") or {})
    label = "no_trade"
    if h1.get("complete") and m5.get("complete"):
        h1_up = float(h1["close"]) >= float(h1["open"])
        m5_up = float(m5["close"]) >= float(m5["open"])
        if h1_up == m5_up:
            label = "trend"
        else:
            label = "range"
        rng = abs(float(m5["close"]) - float(m5["open"]))
        if rng <= 0:
            label = "noise"
    return {
        "schema": "regime.v1",
        "label": label,
        "used_tfs": used,
        "lookahead": False,
        "source": "resampled_completed_bars",
    }
