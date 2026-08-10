#!/usr/bin/env python3
"""Unit tests for the EMA/ATR pullback-confirmation basket scalp."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.pulse import prepare_pulse, sig_pulse


def _cfg(**overrides):
    cfg = {
        "session_start_utc": 0,
        "session_end_utc": 24,
        "cafb_exclude_hours_utc": [],
        "pulse_regime_mode": "range",
        "pulse_z_atr": 0.5,
        "pulse_rsi_edge": 45,
        "pulse_sl_atr": 3.0,
        "pulse_tp_atr": 0.5,
        "spread_bps": 0.4,
        "slippage_bps": 0.2,
        "commission_bps": 0.0,
        "cost_buffer": 1.0,
    }
    cfg.update(overrides)
    return cfg


def test_range_turn_from_below_ema_buys() -> None:
    row = pd.Series(
        {
            "time": pd.Timestamp("2024-01-02 10:00", tz="UTC"),
            "close": 99.5,
            "pulse_close_prev": 99.3,
            "ema_20": 100.0,
            "atr": 1.0,
            "rsi": 40.0,
            "cafb_htf_regime": "range",
        }
    )
    sig = sig_pulse(row, _cfg())
    assert sig is not None and sig.side == "buy"
    assert sig.sl < sig.entry < sig.tp


def test_pulse_cost_gate_rejects_tiny_target() -> None:
    row = pd.Series(
        {
            "time": pd.Timestamp("2024-01-02 10:00", tz="UTC"),
            "close": 99.5,
            "pulse_close_prev": 99.3,
            "ema_20": 100.0,
            "atr": 0.01,
            "rsi": 40.0,
            "cafb_htf_regime": "range",
        }
    )
    assert sig_pulse(row, _cfg(spread_bps=20, slippage_bps=10, cost_buffer=2)) is None


def test_pulse_prepare_has_no_future_leak() -> None:
    n = 120
    close = 100 + np.sin(np.arange(n) / 8.0)
    raw = pd.DataFrame(
        {
            "time": pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC"),
            "open": close,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1.0,
        }
    )
    cfg = _cfg(cafb_context_minutes=5, cafb_htf_fast=3, cafb_htf_slow=5, cafb_htf_adx_min=0)
    first = prepare_pulse(raw, cfg)
    changed = raw.copy()
    changed.loc[n - 1, ["open", "high", "low", "close"]] = [500, 510, 490, 505]
    second = prepare_pulse(changed, cfg)
    cols = ["ema_20", "pulse_close_prev", "cafb_htf_ema_fast", "cafb_htf_ema_slow"]
    pd.testing.assert_frame_equal(first.loc[: n - 2, cols], second.loc[: n - 2, cols])


if __name__ == "__main__":
    test_range_turn_from_below_ema_buys()
    test_pulse_cost_gate_rejects_tiny_target()
    test_pulse_prepare_has_no_future_leak()
    print("ALL PULSE UNIT TESTS PASSED")

