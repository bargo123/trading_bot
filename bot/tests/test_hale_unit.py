#!/usr/bin/env python3
"""Hand-derived unit tests for Heikin-Ashi Level Exhaustion."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.hale import heikin_ashi, prepare_hale, sig_hale_fade, sig_hale_pullback
from aegis.strategy import prepare, signal_from_row


def _ohlc(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "time": pd.Timestamp(ts, tz="UTC"),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 1,
            }
            for ts, open_, high, low, close in rows
        ]
    )


def _cfg() -> dict:
    return {
        "ema_fast": 3,
        "ema_slow": 5,
        "atr_period": 2,
        "rsi_period": 2,
        "bb_period": 2,
        "bb_std": 2.0,
        "adx_period": 2,
        "adx_trend_threshold": 20,
        "cafb_context_minutes": 5,
        "cafb_htf_fast": 2,
        "cafb_htf_slow": 3,
        "cafb_htf_adx_period": 2,
        "cafb_htf_adx_min": 20,
        "hale_round_grid": 0.5,
    }


def test_heikin_ashi_uses_recursive_signal_prices() -> None:
    raw = _ohlc(
        [
            ("2024-01-01 00:00", 10.0, 13.0, 9.0, 12.0),
            ("2024-01-01 00:01", 12.0, 14.0, 10.0, 13.0),
            ("2024-01-01 00:02", 13.0, 15.0, 11.0, 14.0),
        ]
    )
    ha = heikin_ashi(raw)
    np.testing.assert_allclose(ha["hale_ha_close"], [11.0, 12.25, 13.25])
    np.testing.assert_allclose(ha["hale_ha_open"], [11.0, 11.0, 11.625])
    np.testing.assert_allclose(ha["hale_ha_high"], [13.0, 14.0, 15.0])
    np.testing.assert_allclose(ha["hale_ha_low"], [9.0, 10.0, 11.0])


def test_previous_day_and_session_levels_exclude_current_bar() -> None:
    raw = _ohlc(
        [
            ("2024-01-01 22:00", 10.0, 11.0, 9.0, 10.0),
            ("2024-01-01 23:00", 10.0, 13.0, 8.0, 12.0),
            ("2024-01-02 00:00", 12.0, 20.0, 7.0, 15.0),
            ("2024-01-02 01:00", 15.0, 16.0, 10.0, 14.0),
        ]
    )
    prepared = prepare_hale(raw, _cfg())
    assert prepared.loc[:1, "hale_prev_day_high"].isna().all()
    assert prepared.loc[:1, "hale_prev_day_low"].isna().all()
    assert prepared.loc[2, "hale_prev_day_high"] == 13.0
    assert prepared.loc[2, "hale_prev_day_low"] == 8.0
    assert pd.isna(prepared.loc[2, "hale_session_high_prior"])
    assert pd.isna(prepared.loc[2, "hale_session_low_prior"])
    assert prepared.loc[3, "hale_session_high_prior"] == 20.0
    assert prepared.loc[3, "hale_session_low_prior"] == 7.0


def test_prepare_hale_is_idempotent() -> None:
    raw = _ohlc(
        [
            ("2024-01-01 00:00", 10.0, 11.0, 9.0, 10.5),
            ("2024-01-01 00:01", 10.5, 12.0, 10.0, 11.5),
            ("2024-01-01 00:02", 11.5, 13.0, 11.0, 12.5),
            ("2024-01-01 00:03", 12.5, 14.0, 12.0, 13.5),
        ]
    )
    once = prepare_hale(raw, _cfg())
    twice = prepare_hale(once, _cfg())
    assert not any(c.endswith("_x") or c.endswith("_y") for c in twice.columns)
    columns = ["hale_ha_open", "hale_ha_close", "hale_round_level"]
    pd.testing.assert_frame_equal(once[columns], twice[columns])


def _signal_cfg(**overrides) -> dict:
    cfg = {
        "starting_equity": 100.0,
        "risk_percent": 2.0,
        "max_gross_leverage": 30.0,
        "min_units": 0.0,
        "unit_step": 0.0,
        "spread_bps": 0.6,
        "slippage_bps": 0.3,
        "commission_bps": 0.0,
        "commission_round_trip_usd": 0.0,
        "cost_buffer": 1.5,
        "hale_impulse_atr": 1.0,
        "hale_contraction_ratio": 0.5,
        "hale_level_atr": 0.5,
        "hale_stop_buffer_atr": 0.1,
        "hale_target_r": 0.7,
        "hale_pullback_near_atr": 1.0,
    }
    cfg.update(overrides)
    return cfg


def _fade_row(**overrides) -> pd.Series:
    row = {
        "time": pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        "close": 1.1000,
        "atr": 0.0010,
        "cafb_htf_regime": "range",
        "hale_ha_color": -1,
        "hale_prev_color": 1,
        "hale_impulse_up": True,
        "hale_impulse_down": False,
        "hale_impulse_displacement": 0.0030,
        "hale_impulse_body_median": 0.0005,
        "hale_last_body": 0.0002,
        "hale_impulse_high": 1.1030,
        "hale_impulse_low": 1.0990,
        "hale_level_distance_up": 0.0001,
        "hale_level_distance_down": 0.0040,
    }
    row.update(overrides)
    return pd.Series(row)


def test_hale_fade_short_requires_exhaustion_at_level_in_range_regime() -> None:
    signal = sig_hale_fade(_fade_row(), _signal_cfg())
    assert signal is not None
    assert signal.side == "sell"
    assert signal.mode == "hale_fade"
    assert signal.reason == "hale_fade_short"
    assert signal.sl > signal.entry > signal.tp


def test_hale_fade_long_is_symmetric() -> None:
    signal = sig_hale_fade(
        _fade_row(
            hale_ha_color=1,
            hale_prev_color=-1,
            hale_impulse_up=False,
            hale_impulse_down=True,
            hale_impulse_high=1.1010,
            hale_impulse_low=1.0970,
            hale_level_distance_up=0.0040,
            hale_level_distance_down=0.0001,
        ),
        _signal_cfg(),
    )
    assert signal is not None
    assert signal.side == "buy"
    assert signal.sl < signal.entry < signal.tp


def test_hale_fade_rejects_trend_missing_level_and_fixed_cost() -> None:
    assert sig_hale_fade(_fade_row(cafb_htf_regime="trend_up"), _signal_cfg()) is None
    assert sig_hale_fade(_fade_row(hale_level_distance_up=np.nan), _signal_cfg()) is None
    assert sig_hale_fade(
        _fade_row(),
        _signal_cfg(commission_round_trip_usd=4.0),
    ) is None


def _pullback_row(**overrides) -> pd.Series:
    row = {
        "time": pd.Timestamp("2024-01-02 10:00", tz="UTC"),
        "close": 1.1000,
        "ema_20": 1.0995,
        "atr": 0.0010,
        "cafb_htf_regime": "trend_up",
        "hale_ha_color": 1,
        "hale_prev_color": -1,
        "hale_pullback_down": True,
        "hale_pullback_up": False,
        "hale_pullback_high": 1.1010,
        "hale_pullback_low": 1.0980,
    }
    row.update(overrides)
    return pd.Series(row)


def test_hale_pullback_resumes_with_lagged_trend() -> None:
    long_signal = sig_hale_pullback(_pullback_row(), _signal_cfg())
    assert long_signal is not None
    assert long_signal.side == "buy"
    assert long_signal.mode == "hale_pullback"
    assert long_signal.sl < long_signal.entry < long_signal.tp

    short_signal = sig_hale_pullback(
        _pullback_row(
            cafb_htf_regime="trend_down",
            hale_ha_color=-1,
            hale_prev_color=1,
            hale_pullback_down=False,
            hale_pullback_up=True,
            hale_pullback_high=1.1020,
            hale_pullback_low=1.0990,
        ),
        _signal_cfg(),
    )
    assert short_signal is not None
    assert short_signal.side == "sell"
    assert short_signal.sl > short_signal.entry > short_signal.tp


def test_hale_pullback_rejects_range_distance_and_fixed_cost() -> None:
    assert sig_hale_pullback(_pullback_row(cafb_htf_regime="range"), _signal_cfg()) is None
    assert sig_hale_pullback(_pullback_row(ema_20=1.0950), _signal_cfg()) is None
    assert sig_hale_pullback(
        _pullback_row(),
        _signal_cfg(commission_round_trip_usd=4.0),
    ) is None


def test_stable_score_prefers_expectancy_over_raw_win_rate() -> None:
    from scripts.tune_hale_basket import stable_score

    positive = {
        "trades": 50,
        "win_rate": 58.0,
        "expectancy_r": 0.10,
        "profit_factor": 1.25,
        "trades_per_day": 8.0,
        "max_drawdown_pct": 8.0,
    }
    negative_high_wr = {
        "trades": 50,
        "win_rate": 92.0,
        "expectancy_r": -0.05,
        "profit_factor": 0.80,
        "trades_per_day": 20.0,
        "max_drawdown_pct": 4.0,
    }
    assert stable_score(positive, positive, 20, 10) > stable_score(
        negative_high_wr,
        negative_high_wr,
        20,
        10,
    )
    assert stable_score({**positive, "trades": 19}, positive, 20, 10) <= -1e8


def test_generic_strategy_router_prepares_hale_for_paper_runner() -> None:
    raw = _ohlc(
        [
            (
                f"2024-01-01 {hour:02d}:00",
                1.1000 + hour * 0.0001,
                1.1003 + hour * 0.0001,
                1.0997 + hour * 0.0001,
                1.1001 + hour * 0.0001,
            )
            for hour in range(12)
        ]
    )
    cfg = {**_cfg(), "signal_mode": "hale_pullback", "hale_pullback_bars": 1}
    frame = prepare(raw, cfg)
    assert "hale_ha_close" in frame
    assert "hale_pullback_down" in frame
    assert signal_from_row(frame.iloc[-1], cfg) == sig_hale_pullback(frame.iloc[-1], cfg)
