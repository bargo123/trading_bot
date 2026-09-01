"""Book-censor gates on the firehose scalp. Not a 100% WR claim."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.features import enrich_all
from aegis.session_algos import _firehose_book_allows, sig_firehose
from aegis.strategy import prepare


def _cfg(**extra):
    base = {
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
        "firehose_pip_size": 0.0001,
        "firehose_tp_pips": 2,
        "firehose_sl_pips": 4,
        "firehose_every_bar": True,
        "firehose_book_filter": True,
        "spread_bps": 0.2,
        "slippage_bps": 0.0,
        "cost_buffer": 1.0,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "er_period": 10,
        "htf_ema_period": 20,
        "firehose_min_er": 0.35,
        "firehose_min_range_pips": 1.0,
    }
    base.update(extra)
    return base


def test_doji_is_blocked_and_body_mismatch_is_blocked():
    row = pd.Series(
        {
            "high": 1.00020,
            "low": 1.00000,
            "open": 1.00000,
            "close": 1.00018,
            "volman_doji": True,
            "kaufman_er": 0.9,
            "htf_ema": 1.00000,
            "impulse_red": False,
            "impulse_green": False,
            "inside_bar": False,
            "prior_high_break": True,
            "nison_hammer": False,
            "nison_bull_engulf": False,
            "nison_shooting_star": False,
            "nison_bear_engulf": False,
            "pin_bull": False,
            "pin_bear": False,
            "volman_box_break_up": True,
        }
    )
    assert not _firehose_book_allows(row, _cfg(), "buy")
    row["volman_doji"] = False
    row["close"] = 0.99990  # bearish body, long request
    assert not _firehose_book_allows(row, _cfg(), "buy")
    row["close"] = 1.00018
    assert _firehose_book_allows(row, _cfg(), "buy")


def test_low_efficiency_and_impulse_red_block_longs():
    row = pd.Series(
        {
            "high": 1.00020,
            "low": 1.00000,
            "open": 1.00000,
            "close": 1.00018,
            "volman_doji": False,
            "kaufman_er": 0.10,
            "htf_ema": 1.00000,
            "impulse_red": False,
            "impulse_green": False,
            "inside_bar": False,
            "prior_high_break": True,
            "nison_hammer": False,
            "nison_bull_engulf": False,
            "nison_shooting_star": False,
            "nison_bear_engulf": False,
            "pin_bull": False,
            "pin_bear": False,
            "volman_box_break_up": True,
        }
    )
    assert not _firehose_book_allows(row, _cfg(), "buy")
    row["kaufman_er"] = 0.9
    row["impulse_red"] = True
    assert not _firehose_book_allows(row, _cfg(), "buy")
    row["impulse_red"] = False
    assert _firehose_book_allows(row, _cfg(), "buy")


def test_trending_frame_can_emit_firehose_with_book_filter():
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
    cfg = _cfg()
    frame = prepare(df, {**cfg, "signal_mode": "firehose"})
    assert "kaufman_er" in frame.columns
    assert "impulse_green" in frame.columns
    sig = sig_firehose(frame.iloc[-2], cfg)
    assert sig is not None
    assert sig.side == "buy"


def test_every_bar_spray_ignores_book_censors_when_filter_off():
    row = pd.Series(
        {
            "time": pd.Timestamp("2026-01-01 12:00", tz="UTC"),
            "open": 1.0,
            "high": 1.00001,
            "low": 0.99999,
            "close": 1.00001,
            "ema_20": 1.0,
            "close_prev": 1.0,
            "high_prev": 1.0,
            "low_prev": 1.0,
            "volman_doji": True,
            "kaufman_er": 0.01,
            "impulse_red": True,
        }
    )
    cfg = _cfg(firehose_book_filter=False)
    sig = sig_firehose(row, cfg)
    assert sig is not None
    assert sig.side == "buy"
    assert sig.reason == "firehose_bar_up"


if __name__ == "__main__":
    test_doji_is_blocked_and_body_mismatch_is_blocked()
    test_low_efficiency_and_impulse_red_block_longs()
    test_trending_frame_can_emit_firehose_with_book_filter()
    test_every_bar_spray_ignores_book_censors_when_filter_off()
    print("OK")
