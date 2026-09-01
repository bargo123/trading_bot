from __future__ import annotations

import pandas as pd
import pytest

from aegis.research.barclips import clips_from_backtest_trades, market_state_columns
from aegis.research.dataset import LookaheadError


def _trades() -> pd.DataFrame:
    rows = []
    for i in range(6):
        rows.append(
            {
                "entry_time": pd.Timestamp("2026-08-10 08:00", tz="UTC") + pd.Timedelta(minutes=i),
                "exit_time": pd.Timestamp("2026-08-10 08:30", tz="UTC") + pd.Timedelta(minutes=i),
                "side": "buy" if i % 2 == 0 else "sell",
                "pnl": 0.05 if i % 2 == 0 else -0.12,
                "r": 0.4 if i % 2 == 0 else -1.0,
                "outcome": "tp" if i % 2 == 0 else "sl",
                "mfe": 1.2,
                "mae": -0.3,
                "bars_held": 30,
                "symbol": "EURUSD",
                "intel_snap": {
                    "kaufman_er": 0.3 + i * 0.01,
                    "rsi": 50.0 + i,
                    "adx": 20.0,
                    "atr": 0.0004,
                    "range_loc": 0.5,
                    "jansen_score": 0.1,
                    "harris_jump": False,
                    "brooks_in_range": True,
                    "time": pd.Timestamp("2026-08-10 08:00", tz="UTC") + pd.Timedelta(minutes=i),
                },
            }
        )
    return pd.DataFrame(rows)


def test_bar_clips_keep_market_state_and_drop_outcome_fields():
    clips = clips_from_backtest_trades(_trades(), data_source="mt5_bars")
    assert len(clips) == 6
    feats = clips[0]["features"]
    assert "kaufman_er" in feats
    assert "rsi" in feats
    assert "hour_utc" in feats
    assert "side_buy" in feats
    for leaked in ("mfe", "mae", "bars_held", "exit_time", "pnl", "r", "outcome"):
        assert leaked not in feats
    assert clips[0]["pnl"] == pytest.approx(0.05)
    assert clips[0]["data_source"] == "mt5_bars"


def test_bar_clips_are_time_ordered():
    shuffled = _trades().iloc[::-1].reset_index(drop=True)
    clips = clips_from_backtest_trades(shuffled, data_source="mt5_bars")
    times = [c["bar"] for c in clips]
    assert times == sorted(times)


def test_bar_clips_reject_leaked_snapshot_field():
    bad = _trades()
    bad.at[0, "intel_snap"] = {"kaufman_er": 0.3, "mfe": 1.2}
    with pytest.raises(LookaheadError, match="lookahead"):
        clips_from_backtest_trades(bad, data_source="mt5_bars")


def test_absolute_price_levels_are_not_features():
    """Raw levels encode symbol identity and drift with time, so they must be dropped."""
    clips = clips_from_backtest_trades(_trades(), data_source="mt5_bars")
    feats = clips[0]["features"]
    for level in ("open", "high", "low", "close", "ema_20", "atr"):
        assert level not in feats, f"{level} is an absolute price level"
    assert "rsi" in feats
    assert "kaufman_er" in feats


def test_market_state_columns_exclude_time_and_bookkeeping():
    cols = market_state_columns(clips_from_backtest_trades(_trades(), data_source="mt5_bars"))
    assert "time" not in cols
    assert "symbol" not in cols
    assert "kaufman_er" in cols
    assert cols == sorted(cols)


def test_backtest_trades_actually_carry_intel_snap():
    from aegis.backtest import run_backtest
    from aegis.optimizer.walk_forward import synthetic_ohlcv

    cfg = {
        "symbol": "EURUSD",
        "timeframe": "1m",
        "signal_mode": "firehose",
        "algo": "firehose",
        "firehose_every_bar": True,
        "firehose_pip_size": 0.0001,
        "firehose_tp_pips": 20,
        "firehose_sl_pips": 10,
        "spread_bps": 0.2,
        "slippage_bps": 0.1,
        "firehose_book_filter": False,
        "firehose_chart_read": False,
        "firehose_jansen_filter": False,
        "firehose_harris_jump": False,
        "firehose_skip_doji": False,
        "ema_fast": 20,
        "ema_slow": 50,
        "volman_ema": 20,
        "er_period": 10,
        "htf_ema_period": 20,
        "adx_period": 14,
        "starting_equity": 1000,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "allow_live": False,
    }
    result = run_backtest(synthetic_ohlcv(600, seed=5), cfg)
    if result.total_trades == 0:
        pytest.skip("synthetic frame produced no trades for this config")
    assert "intel_snap" in result.trades.columns
    snap = result.trades["intel_snap"].iloc[0]
    assert isinstance(snap, dict)
    assert "kaufman_er" in snap
