from __future__ import annotations

import pandas as pd
import pytest

from aegis.intel.firehose_brain import video_style_micro_candidate
from aegis.research.video_style_paper import (
    VideoStyleConfig,
    video_style_geometry,
    video_style_scale_allowed,
    video_style_signal,
)


def _bars(*, first_close: float, second_close: float, symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="min", tz="UTC"),
            "open": [first_close, first_close],
            "high": [first_close + 0.001, max(first_close + 0.003, second_close + 0.001)],
            "low": [first_close - 0.001, min(first_close - 0.003, second_close - 0.001)],
            "close": [first_close, second_close],
        }
    )


def test_video_style_signal_is_symbol_agnostic_and_uses_completed_breakout_bar():
    for symbol, first, second, side in (
        ("EURUSD", 1.1000, 1.1040, "buy"),
        ("USDJPY", 150.00, 149.90, "sell"),
        ("XAUUSD", 2350.0, 2355.0, "buy"),
    ):
        bars = _bars(first_close=first, second_close=second, symbol=symbol)
        signal = video_style_signal(bars, symbol=symbol)

        assert signal is not None
        assert signal.symbol == symbol
        assert signal.side == side
        assert signal.signal_time == bars.iloc[-1]["time"]
        assert signal.risk_distance > 0


def test_video_style_geometry_is_shared_by_simulator_and_firehose_candidate():
    cfg = VideoStyleConfig(stop_r=0.5, reward_to_risk=3.0)
    bars = _bars(first_close=1.1000, second_close=1.1040, symbol="EURUSD")
    signal = video_style_signal(bars, symbol="EURUSD")
    assert signal is not None

    entry = 1.1042
    stop, target = video_style_geometry(signal, entry_price=entry, cfg=cfg)
    candidate = video_style_micro_candidate(
        signal,
        entry_price=entry,
        pip=0.0001,
        spread_pips=0.8,
        cfg=cfg,
    )

    assert candidate.side == signal.side
    assert candidate.invalidation == stop
    assert candidate.target == target
    assert candidate.family == "video_style_breakout"
    assert candidate.symbol == "EURUSD"
    assert candidate.max_hold_s == cfg.max_hold_s


def test_video_style_config_rejects_non_positive_seconds_horizon():
    with pytest.raises(ValueError, match="max_hold_s"):
        VideoStyleConfig(max_hold_s=0)


def test_video_style_scale_requires_profit_favorable_move_and_capacity():
    kwargs = {
        "side": "buy",
        "last_entry_price": 100.0,
        "current_price": 100.5,
        "stop_distance": 1.0,
        "unrealized_pnl": 0.5,
        "current_layers": 1,
        "max_layers": 2,
        "scale_after_r": 0.5,
    }
    assert video_style_scale_allowed(**kwargs)
    assert not video_style_scale_allowed(**{**kwargs, "unrealized_pnl": -0.1})
    assert not video_style_scale_allowed(**{**kwargs, "current_price": 99.5})
    assert not video_style_scale_allowed(**{**kwargs, "current_layers": 2})


def test_video_style_signal_requires_a_breakout():
    bars = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=2, freq="min", tz="UTC"),
            "open": [1.1, 1.1],
            "high": [1.101, 1.101],
            "low": [1.099, 1.099],
            "close": [1.100, 1.1005],
        }
    )
    assert video_style_signal(bars, symbol="GBPUSD") is None
