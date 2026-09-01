#!/usr/bin/env python3
"""Unit tests for the Cost-Aware Failed-Break signal."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.cafb import prepare_cafb, sig_cafb


def _cfg(**overrides):
    cfg = {
        "cafb_context_minutes": 5,
        "cafb_box_bars": 4,
        "cafb_box_max_atr": 3.0,
        "cafb_box_min_atr": 0.1,
        "cafb_htf_fast": 3,
        "cafb_htf_slow": 5,
        "cafb_htf_adx_min": 0,
        "cafb_target_mode": "opposite",
        "cafb_stop_buffer_atr": 0.1,
        "cafb_min_rr": 0.1,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "spread_bps": 0.5,
        "slippage_bps": 0.25,
        "cost_buffer": 1.0,
    }
    cfg.update(overrides)
    return cfg


def test_failed_down_break_in_uptrend_buys() -> None:
    row = pd.Series(
        {
            "time": pd.Timestamp("2024-01-02 10:00", tz="UTC"),
            "close": 100.5,
            "high": 101.0,
            "low": 98.5,
            "atr": 1.0,
            "cafb_box_low": 99.0,
            "cafb_box_high": 102.0,
            "cafb_box_mid": 100.5,
            "cafb_compressed": True,
            "cafb_failed_dn": True,
            "cafb_failed_up": False,
            "cafb_htf_regime": "trend_up",
        }
    )
    sig = sig_cafb(row, _cfg())
    assert sig is not None
    assert sig.side == "buy"
    assert sig.sl < sig.entry < sig.tp


def test_cost_gate_rejects_too_small_target() -> None:
    row = pd.Series(
        {
            "time": pd.Timestamp("2024-01-02 10:00", tz="UTC"),
            "close": 100.5,
            "high": 101.0,
            "low": 98.5,
            "atr": 1.0,
            "cafb_box_low": 99.0,
            "cafb_box_high": 100.51,
            "cafb_box_mid": 100.505,
            "cafb_compressed": True,
            "cafb_failed_dn": True,
            "cafb_failed_up": False,
            "cafb_htf_regime": "trend_up",
        }
    )
    assert sig_cafb(row, _cfg(spread_bps=20.0, slippage_bps=10.0, cost_buffer=2.0)) is None


def test_future_bar_does_not_change_past_features() -> None:
    n = 120
    close = 100 + np.sin(np.arange(n) / 8.0)
    raw = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC"),
            "open": close,
            "high": close + 0.3,
            "low": close - 0.3,
            "close": close,
            "volume": 1.0,
        }
    )
    first = prepare_cafb(raw, _cfg())
    changed = raw.copy()
    changed.loc[n - 1, ["open", "high", "low", "close"]] = [500, 510, 490, 505]
    second = prepare_cafb(changed, _cfg())
    cols = ["cafb_box_low", "cafb_box_high", "cafb_htf_ema_fast", "cafb_htf_ema_slow"]
    pd.testing.assert_frame_equal(first.loc[: n - 2, cols], second.loc[: n - 2, cols])


if __name__ == "__main__":
    test_failed_down_break_in_uptrend_buys()
    test_cost_gate_rejects_too_small_target()
    test_future_bar_does_not_change_past_features()
    print("ALL CAFB UNIT TESTS PASSED")

