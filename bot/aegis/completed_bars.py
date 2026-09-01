"""Canonical completed OHLCV bars shared by runtime and research."""
from __future__ import annotations

import pandas as pd


TF_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
_OHLCV_AGGREGATIONS = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


def normalize_completed_m1(m1: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize completed MT5 M1 bars without inventing gaps."""
    required = {"time", *_OHLCV_COLUMNS}
    missing = sorted(required - set(m1.columns))
    if missing:
        raise ValueError(f"completed M1 bars missing columns: {missing}")
    frame = m1.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").reset_index(drop=True)
    if frame["time"].duplicated().any():
        raise ValueError("completed M1 bars contain duplicate timestamps")
    return frame


def resample_completed(m1: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Aggregate completed M1 bars into complete period-start-labelled OHLCV bars."""
    try:
        minutes = TF_MINUTES[tf]
    except KeyError as exc:
        raise ValueError(f"unsupported timeframe: {tf}") from exc
    frame = normalize_completed_m1(m1)
    if minutes == 1:
        return frame

    grouped = (
        frame.set_index("time")
        .resample(f"{minutes}min", label="left", closed="left")
        .agg(_OHLCV_AGGREGATIONS)
        .dropna(subset=["close"])
    )
    last_m1_open = grouped.index + pd.Timedelta(minutes=minutes - 1)
    complete = last_m1_open.isin(frame["time"])
    return grouped.loc[complete].reset_index()
