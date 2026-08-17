"""Tick replay into completed M1. No lookahead: a minute is closed only after a later tick."""
from __future__ import annotations

import pandas as pd

from aegis.research.dataplane import ticks_frame


def m1_from_ticks(ticks: pd.DataFrame) -> pd.DataFrame:
    """Build completed M1 OHLCV from a broker tick stream.

    The last minute is dropped unless a tick exists at or after that minute + 1s
    into the next minute (i.e. the bar is known closed). Tick volume is a
    broker proxy, not centralized FX volume.
    """
    if ticks.empty:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    d = ticks_frame(ticks.to_dict("records")) if "seq" in ticks.columns else ticks.copy()
    d["ts_utc"] = pd.to_datetime(d["ts_utc"], utc=True)
    d = d.sort_values(["ts_utc", "seq"] if "seq" in d.columns else ["ts_utc"])
    last_ts = d["ts_utc"].max()
    d["minute"] = d["ts_utc"].dt.floor("min")
    mid = (d["bid"].astype(float) + d["ask"].astype(float)) / 2.0
    d["px"] = d["last"].where(d["last"].astype(float) > 0, mid)
    g = d.groupby("minute", sort=True)
    bars = pd.DataFrame(
        {
            "time": g.size().index,
            "open": g["px"].first().to_numpy(),
            "high": g["px"].max().to_numpy(),
            "low": g["px"].min().to_numpy(),
            "close": g["px"].last().to_numpy(),
            "volume": g["tick_volume"].sum().to_numpy() if "tick_volume" in d.columns else g.size().to_numpy(),
        }
    )
    complete = bars["time"] + pd.Timedelta(minutes=1) <= last_ts
    out = bars.loc[complete].reset_index(drop=True)
    out.attrs["volume_kind"] = "broker_tick_volume_proxy"
    return out
