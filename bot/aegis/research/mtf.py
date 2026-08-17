"""Genuine multi-timeframe state from completed resampled bars. Not M1 EMA aliases."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aegis.research.dataplane import TF_MINUTES, resample_completed


def mtf_state(m1: pd.DataFrame) -> dict[str, Any]:
    frames = {tf: resample_completed(m1, tf) for tf in TF_MINUTES}
    last: dict[str, Any] = {"schema": "mtf.v1", "lookahead": False}
    for tf, df in frames.items():
        last[tf] = {
            "n": int(len(df)),
            "complete": bool(len(df) > 0),
            "time": None if df.empty else str(df["time"].iloc[-1]),
            "close": None if df.empty else float(df["close"].iloc[-1]),
            "open": None if df.empty else float(df["open"].iloc[-1]),
        }
    last["frames"] = frames
    return last


def require_htf(state: dict[str, Any], *tfs: str) -> bool:
    return all(bool((state.get(tf) or {}).get("complete")) for tf in tfs)
