#!/usr/bin/env python3
"""Unit tests for Fabris NTZ features + Fuller pyramid stop math (no network)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.profile_features import add_fabris_ntz_features
from aegis.pyramid import next_pyramid_sl, should_pyramid


def _bars() -> pd.DataFrame:
    """Synthetic UTC day: quiet Asia, NTZ 07-08 range 100-110, then break up."""
    rows = []
    # 06:00–06:45
    for m in range(0, 60, 15):
        t = pd.Timestamp(f"2024-06-03 06:{m:02d}:00", tz="UTC")
        rows.append({"time": t, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1, "atr": 5.0})
    # NTZ 07:00–07:45 → high 110, low 100
    ntz = [(100, 105, 100, 104), (104, 108, 103, 107), (107, 110, 106, 109), (109, 110, 108, 109)]
    for i, (o, h, l, c) in enumerate(ntz):
        t = pd.Timestamp(f"2024-06-03 07:{i*15:02d}:00", tz="UTC")
        rows.append({"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 1, "atr": 5.0})
    # 08:00+ breakout
    after = [
        (109, 111, 108, 110.5),  # still inside-ish
        (110.5, 112, 110, 111.5),  # break above 110
        (111.5, 113, 111, 112.5),
    ]
    for i, (o, h, l, c) in enumerate(after):
        t = pd.Timestamp(f"2024-06-03 08:{i*15:02d}:00", tz="UTC")
        rows.append({"time": t, "open": o, "high": h, "low": l, "close": c, "volume": 1, "atr": 5.0})
    return pd.DataFrame(rows)


def test_ntz_range_and_break() -> None:
    cfg = {
        "ntz_start_utc": 7,
        "ntz_end_utc": 8,
        "ntz_min_atr": 0.5,
        "ntz_max_atr": 5.0,
        "ntz_asia_max_pct": 1.0,  # loose for tiny synthetic Asia
    }
    out = add_fabris_ntz_features(_bars(), cfg)
    ready = out[out["ntz_ready"]]
    assert not ready.empty, "NTZ should be ready after 08:00"
    assert abs(float(ready.iloc[0]["ntz_high"]) - 110.0) < 1e-9
    assert abs(float(ready.iloc[0]["ntz_low"]) - 100.0) < 1e-9
    assert abs(float(ready.iloc[0]["ntz_width"]) - 10.0) < 1e-9
    assert bool(ready.iloc[0]["ntz_width_ok"])
    breaks = out[out["ntz_break_up"]]
    assert len(breaks) >= 1, "expected at least one NTZ upside break"
    assert float(breaks.iloc[0]["close"]) > 110.0


def test_fuller_pyramid_stops() -> None:
    # Sell example mirroring Fuller: E0=1.2550, add@1.2450 → SL=1.2550; add@1.2350 → SL=1.2450
    assert next_pyramid_sl("sell", entries=[1.2550], new_entry=1.2450) == 1.2550
    assert next_pyramid_sl("sell", entries=[1.2550, 1.2450], new_entry=1.2350) == 1.2450
    assert next_pyramid_sl("buy", entries=[100.0], new_entry=110.0) == 100.0
    assert next_pyramid_sl("buy", entries=[100.0, 110.0], new_entry=120.0) == 110.0


def test_should_pyramid_gates() -> None:
    assert should_pyramid(
        side="buy",
        entry=100.0,
        price=110.0,
        initial_risk=10.0,
        adds=0,
        max_adds=2,
        add_r=1.0,
        adx=30.0,
        adx_min=25.0,
        enabled=True,
    )
    assert not should_pyramid(
        side="buy",
        entry=100.0,
        price=105.0,  # only +0.5R
        initial_risk=10.0,
        adds=0,
        max_adds=2,
        add_r=1.0,
        adx=30.0,
        adx_min=25.0,
        enabled=True,
    )
    assert not should_pyramid(
        side="buy",
        entry=100.0,
        price=110.0,
        initial_risk=10.0,
        adds=0,
        max_adds=2,
        add_r=1.0,
        adx=10.0,  # weak trend
        adx_min=25.0,
        enabled=True,
    )


if __name__ == "__main__":
    test_ntz_range_and_break()
    test_fuller_pyramid_stops()
    test_should_pyramid_gates()
    print("ALL UNIT TESTS PASSED")
