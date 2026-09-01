"""Steidlmayer-style TPO from completed M30. Not CME pit IB; not order flow."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aegis.research.dataplane import resample_completed


def tpo_profile(m1: pd.DataFrame, *, bins: int = 24) -> dict[str, Any]:
    """Build a session TPO from completed M1 of the last UTC day.

    Initial balance is the first two *completed* M30 bars of that UTC day — a
    forex-session proxy, not Steidlmayer's CME pit first hour. Tick occupancy
    is time-at-price, not exchange volume.
    """
    empty = {
        "ok": False,
        "kind": "tpo_time_at_price_proxy",
        "pit_session": False,
        "order_flow": False,
    }
    if m1.empty:
        return empty
    d = m1.copy()
    d["time"] = pd.to_datetime(d["time"], utc=True)
    day = d["time"].dt.floor("D").iloc[-1]
    sess = d.loc[d["time"].dt.floor("D") == day]
    m30 = resample_completed(sess, "M30")
    if len(m30) < 3:
        return empty
    lo = float(sess["low"].min())
    hi = float(sess["high"].max())
    if hi <= lo:
        return empty
    edges = np.linspace(lo, hi, bins + 1)
    tpos = np.zeros(bins, dtype=int)
    for _, bar in m30.iterrows():
        touched = (edges[1:] >= float(bar["low"])) & (edges[:-1] <= float(bar["high"]))
        tpos += touched.astype(int)
    if int(tpos.sum()) <= 0:
        return empty
    poc = int(np.argmax(tpos))
    order = np.argsort(-tpos)
    target = 0.70 * float(tpos.sum())
    covered = 0.0
    va_idx: list[int] = []
    for i in order:
        va_idx.append(int(i))
        covered += float(tpos[i])
        if covered >= target:
            break
    va_lo = float(edges[min(va_idx)])
    va_hi = float(edges[max(va_idx) + 1])
    ib = m30.head(2)
    singles = [i for i, n in enumerate(tpos) if n == 1]
    excess_hi = bool(singles and max(singles) >= bins - 2)
    excess_lo = bool(singles and min(singles) <= 1)
    return {
        "ok": True,
        "kind": "tpo_time_at_price_proxy",
        "pit_session": False,
        "order_flow": False,
        "poc": float((edges[poc] + edges[poc + 1]) / 2.0),
        "va_low": va_lo,
        "va_high": va_hi,
        "ib_low": float(ib["low"].min()),
        "ib_high": float(ib["high"].max()),
        "excess_high": excess_hi,
        "excess_low": excess_lo,
        "n_m30": int(len(m30)),
    }


def volume_at_price(ticks: pd.DataFrame, *, bins: int = 24) -> dict[str, Any]:
    """Histogram of broker tick volume by mid price. Not centralized FX volume."""
    empty = {
        "ok": False,
        "kind": "volume_at_price_broker_tick_proxy",
        "centralized_volume": False,
        "order_flow": False,
    }
    if ticks is None or ticks.empty:
        return empty
    d = ticks.copy()
    d["ts_utc"] = pd.to_datetime(d["ts_utc"], utc=True)
    mid = (d["bid"].astype(float) + d["ask"].astype(float)) / 2.0
    vol = d["tick_volume"].astype(float) if "tick_volume" in d.columns else pd.Series(1.0, index=d.index)
    lo = float(mid.min())
    hi = float(mid.max())
    if hi <= lo or float(vol.sum()) <= 0:
        return empty
    edges = np.linspace(lo, hi, bins + 1)
    hist, _ = np.histogram(mid.to_numpy(), bins=edges, weights=vol.to_numpy())
    if float(hist.sum()) <= 0:
        return empty
    poc = int(np.argmax(hist))
    return {
        "ok": True,
        "kind": "volume_at_price_broker_tick_proxy",
        "centralized_volume": False,
        "order_flow": False,
        "poc": float((edges[poc] + edges[poc + 1]) / 2.0),
        "n_ticks": int(len(d)),
        "volume_kind": "broker_tick_volume_proxy",
    }
