"""Nison/Volman chart-read gates. Not a 100% accuracy claim."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.chart_read import add_chart_features, chart_confirms
from aegis.strategy import prepare


def test_inside_bar_and_opposing_engulf_block():
    row = pd.Series(
        {
            "inside_bar": True,
            "nison_hammer": False,
            "nison_bull_engulf": False,
            "pin_bull": False,
            "volman_box_break_up": True,
            "prior_high_break": True,
            "nison_shooting_star": False,
            "nison_bear_engulf": False,
            "pin_bear": False,
        }
    )
    assert not chart_confirms(row, {"firehose_chart_read": True}, "buy")
    row["inside_bar"] = False
    row["nison_bear_engulf"] = True
    assert not chart_confirms(row, {"firehose_chart_read": True}, "buy")
    row["nison_bear_engulf"] = False
    assert chart_confirms(row, {"firehose_chart_read": True}, "buy")


def test_bull_engulfing_detected_on_two_bars():
    df = pd.DataFrame(
        {
            "open": [1.10, 1.09],
            "high": [1.11, 1.12],
            "low": [1.08, 1.085],
            "close": [1.09, 1.115],
        }
    )
    out = add_chart_features(df, {})
    assert bool(out.iloc[-1]["nison_bull_engulf"])
    assert not bool(out.iloc[-1]["nison_bear_engulf"])


def test_prepare_adds_chart_columns():
    n = 80
    close = [1.0 + i * 0.00015 for i in range(n)]
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC"),
            "open": [c - 0.00012 for c in close],
            "high": [c + 0.00002 for c in close],
            "low": [c - 0.00014 for c in close],
            "close": close,
            "volume": [100] * n,
        }
    )
    frame = prepare(
        df,
        {
            "ema_fast": 20,
            "ema_slow": 200,
            "atr_period": 14,
            "rsi_period": 14,
            "bb_period": 20,
            "bb_std": 2.0,
            "donchian_period": 20,
            "adx_period": 14,
            "adx_trend_threshold": 25,
            "volman_ema": 20,
            "signal_mode": "firehose",
            "er_period": 10,
            "htf_ema_period": 20,
        },
    )
    assert "nison_bull_engulf" in frame.columns
    assert "inside_bar" in frame.columns
    assert "prior_high_break" in frame.columns
    # Steady uptrend closes above prior high.
    assert bool(frame.iloc[-2]["prior_high_break"])


def test_break_retest_bull_after_prior_break():
    df = pd.DataFrame(
        {
            "open": [1.095, 1.101, 1.112],
            "high": [1.100, 1.120, 1.118],
            "low": [1.090, 1.100, 1.098],
            "close": [1.095, 1.115, 1.112],
        }
    )
    out = add_chart_features(df, {})
    assert bool(out.iloc[-1]["break_retest_bull"])
    assert not bool(out.iloc[-1]["break_retest_bear"])
