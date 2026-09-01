"""Selective MTF price-action (pa_select). Not a 100% or 90% winrate claim."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.chart_read import add_chart_features
from aegis.config import load_config
from aegis.features import classify_structure, round_above, round_below
from aegis.pa_select import fetch_mtf_frames, prepare_pa_select, sig_pa_select
from aegis.strategy import prepare, signal_from_row


def _cfg(**overrides):
    cfg = {
        "symbol": "EURUSD",
        "signal_mode": "pa_select",
        "algo": "pa_select",
        "firehose_pip_size": 0.0001,
        "jpy_pip_size": 0.01,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "spread_bps": 0.5,
        "slippage_bps": 0.25,
        "cost_buffer": 1.0,
        "pa_min_er": 0.30,
        "pa_range_min_er": 0.0,
        "pa_allow_trend": True,
        "pa_allow_range": True,
        "pa_require_h1": True,
        "pa_elder_censor": True,
        "pa_allow_pin": True,
        "pa_allow_engulf": True,
        "pa_allow_retest": True,
        "pa_zone_pips": 8.0,
        "pa_sl_buffer_pips": 1.0,
        "pa_max_sl_pips": 12.0,
        "pa_min_sl_pips": 0.0,
        "pa_tp_mode": "r_multiple",
        "pa_tp_r": 4.0,
        "pa_tp_pips": 20.0,
        "min_rr": 2.0,
        "pa_require_multi_touch": False,
        "pa_daily_mode": "ema",
    }
    cfg.update(overrides)
    return cfg


def _row(**overrides):
    data = {
        "time": pd.Timestamp("2026-03-10 12:00", tz="UTC"),
        "open": 1.10020,
        "high": 1.10055,
        "low": 1.10000,
        "close": 1.10050,
        "atr": 0.00040,
        "kaufman_er": 0.55,
        "pin_bull": True,
        "pin_bear": False,
        "nison_hammer": True,
        "nison_shooting_star": False,
        "nison_bull_engulf": False,
        "nison_bear_engulf": False,
        "break_retest_bull": False,
        "break_retest_bear": False,
        "inside_bar": False,
        "impulse_red": False,
        "impulse_green": False,
        "pa_d1_dir": "up",
        "pa_d1_structure": "trend_up",
        "pa_h4_structure": "trend_up",
        "pa_h1_dir": "up",
        "pa_support": 1.10000,
        "pa_resist": 1.10400,
        "pa_support_touches": 2,
        "pa_resist_touches": 1,
    }
    data.update(overrides)
    return pd.Series(data)


def test_structure_hh_hl_is_uptrend():
    assert classify_structure(1.12, 1.10, 1.08, 1.06, 0.0015) == "trend_up"
    assert classify_structure(1.10, 1.12, 1.06, 1.08, 0.0015) == "trend_down"
    assert classify_structure(1.1005, 1.1010, 1.0905, 1.0900, 0.0015) == "range"
    assert classify_structure(1.1010, 1.1005, 1.0905, 1.0900, 0.0015) == "range"
    assert classify_structure(1.12, 1.10, 1.06, 1.08, 0.0015) == "chop"


def test_round_numbers_are_pip_aware():
    eur_step = 0.0001 * 100
    assert abs(round_below(1.10750, eur_step) - 1.10000) < 1e-12
    assert abs(round_above(1.10750, eur_step) - 1.11000) < 1e-12
    jpy_step = 0.01 * 100
    assert abs(round_below(150.35, jpy_step) - 150.0) < 1e-12
    assert abs(round_above(150.35, jpy_step) - 151.0) < 1e-12


def test_pin_at_support_in_uptrend_buys():
    sig = sig_pa_select(_row(), _cfg())
    assert sig is not None
    assert sig.side == "buy"
    assert sig.mode == "pa_select"
    assert "100" not in sig.reason
    assert sig.sl < float(_row()["low"])
    assert sig.tp > sig.entry


def test_engulf_at_resistance_in_downtrend_sells():
    row = _row(
        pin_bull=False,
        nison_hammer=False,
        nison_bear_engulf=True,
        open=1.10380,
        high=1.10400,
        low=1.10320,
        close=1.10330,
        pa_d1_dir="down",
        pa_d1_structure="trend_down",
        pa_h4_structure="trend_down",
        pa_h1_dir="down",
        pa_support=1.09800,
        pa_resist=1.10400,
        impulse_green=False,
        impulse_red=False,
    )
    sig = sig_pa_select(row, _cfg())
    assert sig is not None
    assert sig.side == "sell"
    assert sig.sl > float(row["high"])
    assert sig.tp < sig.entry


def test_chop_or_low_er_skips():
    assert sig_pa_select(_row(pa_h4_structure="chop"), _cfg()) is None
    assert sig_pa_select(_row(kaufman_er=0.05), _cfg()) is None


def test_mtf_disagreement_skips():
    assert sig_pa_select(_row(pa_h4_structure="trend_down"), _cfg()) is None
    assert sig_pa_select(_row(pa_d1_dir="down"), _cfg()) is None
    assert sig_pa_select(_row(pa_h1_dir="down"), _cfg()) is None


def test_stop_is_beyond_wick_and_never_widened():
    row = _row()
    sig = sig_pa_select(row, _cfg(pa_sl_buffer_pips=1.0))
    assert sig is not None
    assert sig.sl <= float(row["low"]) - 0.0001 + 1e-12
    wide = _row(low=1.09800, close=1.10050, pa_support=1.09800)
    assert sig_pa_select(wide, _cfg(pa_max_sl_pips=5.0)) is None


def test_fetch_mtf_frames_uses_injected_without_engine():
    d1 = pd.DataFrame(
        {
            "time": [pd.Timestamp("2026-01-01", tz="UTC")],
            "open": [1.1],
            "high": [1.11],
            "low": [1.09],
            "close": [1.105],
        }
    )
    frames = fetch_mtf_frames(None, "EURUSD", {"pa_mtf_frames": {"d1": d1}})
    assert "d1" in frames
    assert abs(float(frames["d1"]["close"].iloc[0]) - 1.105) < 1e-12


def test_fetch_mtf_frames_calls_engine_when_not_injected():
    calls = []

    class _Eng:
        def bars(self, symbol, timeframe, lookback_days):
            calls.append((symbol, timeframe, lookback_days))
            return [
                SimpleNamespace(
                    time=pd.Timestamp("2026-01-01", tz="UTC"),
                    open=1.1,
                    high=1.11,
                    low=1.09,
                    close=1.105,
                    volume=1.0,
                )
            ]

    frames = fetch_mtf_frames(_Eng(), "EURUSD", {})
    assert {c[1] for c in calls} >= {"d1", "h4", "h1"}
    assert set(frames) >= {"d1", "h4", "h1"}


def _ohlc(n: int, start: float = 1.10, drift: float = 0.00005) -> pd.DataFrame:
    close = [start + i * drift for i in range(n)]
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
            "open": [c - 0.00010 for c in close],
            "high": [c + 0.00012 for c in close],
            "low": [c - 0.00014 for c in close],
            "close": close,
            "volume": [1.0] * n,
        }
    )


def test_prepare_merges_injected_htf_frames():
    entry = _ohlc(80)
    d1 = _ohlc(40, start=1.08, drift=0.0008)
    d1["time"] = pd.date_range("2025-11-01", periods=40, freq="D", tz="UTC")
    h4 = _ohlc(60, start=1.09, drift=0.0002)
    h4["time"] = pd.date_range("2025-12-01", periods=60, freq="4h", tz="UTC")
    h1 = _ohlc(80, start=1.095, drift=0.00008)
    h1["time"] = pd.date_range("2026-01-01", periods=80, freq="h", tz="UTC")
    cfg = _cfg(
        ema_fast=10,
        ema_slow=20,
        atr_period=14,
        rsi_period=14,
        bb_period=20,
        bb_std=2.0,
        donchian_period=20,
        adx_period=14,
        volman_ema=20,
        er_period=10,
        htf_ema_period=20,
        pa_mtf_frames={"d1": d1, "h4": h4, "h1": h1},
    )
    frame = prepare(entry, cfg)
    assert "pa_h4_structure" in frame.columns
    assert "pa_d1_dir" in frame.columns
    assert "pa_support" in frame.columns
    assert "nison_bull_engulf" in frame.columns
    assert "kaufman_er" in frame.columns
    routed = signal_from_row(frame.iloc[-2], cfg)
    assert routed is None or routed.mode == "pa_select"


def test_break_retest_detected_on_three_bars():
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


def test_config_loads_demo_only_not_firehose():
    cfg = load_config(ROOT / "config_mt5_demo_pa_select.yaml")
    assert cfg["engine"] == "mt5"
    assert cfg["mode"] == "mt5_demo"
    assert cfg["allow_live"] is False
    assert cfg["paper_trading_enabled"] is True
    assert cfg["dry_run"] is False
    assert cfg["firehose_every_bar"] is False
    assert cfg["signal_mode"] == "pa_select"
    assert cfg["algo"] == "pa_select"
    assert float(cfg["order_quantity"]) == 0.01
    assert float(cfg["risk_percent"]) == 1
    assert float(cfg["mt5_max_lots"]) == 0.10
    assert int(cfg["max_positions"]) == 1
    assert int(cfg["ntz_max_trades_day"]) == 3
    assert cfg["scratch_losers"] is False
    assert cfg["pyramid_enabled"] is False
    assert "100" not in str(cfg["test_name"]).lower()
    assert "perfect" not in str(cfg["test_name"]).lower()


if __name__ == "__main__":
    test_structure_hh_hl_is_uptrend()
    test_round_numbers_are_pip_aware()
    test_pin_at_support_in_uptrend_buys()
    test_engulf_at_resistance_in_downtrend_sells()
    test_chop_or_low_er_skips()
    test_mtf_disagreement_skips()
    test_stop_is_beyond_wick_and_never_widened()
    test_fetch_mtf_frames_uses_injected_without_engine()
    test_fetch_mtf_frames_calls_engine_when_not_injected()
    test_prepare_merges_injected_htf_frames()
    test_break_retest_detected_on_three_bars()
    test_config_loads_demo_only_not_firehose()
    print("OK")
