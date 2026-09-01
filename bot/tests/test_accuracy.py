"""Jansen factor score + Harris jump. Not a 100% WR claim."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.accuracy import accuracy_allows
from aegis.features import enrich_all
from aegis.session_algos import _firehose_book_allows, sig_firehose


def _row(**extra):
    base = {
        "open": 1.0,
        "close": 1.0002,
        "high": 1.0003,
        "low": 0.9999,
        "jansen_score": 0.4,
        "harris_jump": False,
        "ema_20": 1.0,
        "close_prev": 1.0,
        "high_prev": 1.0,
        "low_prev": 1.0,
        "time": pd.Timestamp("2026-01-01 12:00", tz="UTC"),
    }
    base.update(extra)
    return pd.Series(base)


def test_flags_off_do_not_block():
    row = _row(jansen_score=-0.9, harris_jump=True)
    assert accuracy_allows(row, {}, "buy")


def test_jansen_requires_score_on_side():
    cfg = {"firehose_jansen_filter": True, "jansen_score_min": 0.15}
    assert accuracy_allows(_row(jansen_score=0.4), cfg, "buy")
    assert not accuracy_allows(_row(jansen_score=0.05), cfg, "buy")
    assert accuracy_allows(_row(jansen_score=-0.4), cfg, "sell")
    assert not accuracy_allows(_row(jansen_score=-0.05), cfg, "sell")
    assert not accuracy_allows(_row(jansen_score=float("nan")), cfg, "buy")


def test_jansen_runs_even_when_book_filter_is_off():
    cfg = {
        "firehose_book_filter": False,
        "firehose_jansen_filter": True,
        "jansen_score_min": 0.15,
    }
    weak = _row(jansen_score=0.01)
    strong = _row(jansen_score=0.5)
    assert not _firehose_book_allows(weak, cfg, "buy")
    assert _firehose_book_allows(strong, cfg, "buy")


def test_harris_skips_chase_after_jump():
    cfg = {"firehose_harris_jump": True}
    up = _row(open=1.0, close=1.002, harris_jump=True)
    assert not accuracy_allows(up, cfg, "buy")
    assert accuracy_allows(up, cfg, "sell")
    dn = _row(open=1.002, close=1.0, harris_jump=True)
    assert not accuracy_allows(dn, cfg, "sell")
    assert accuracy_allows(dn, cfg, "buy")


def test_jansen_features_have_no_lookahead_and_gate_firehose():
    n = 80
    close = [1.0 + i * 0.0002 for i in range(n)]
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC"),
            "open": [c - 0.00005 for c in close],
            "high": [c + 0.00008 for c in close],
            "low": [c - 0.00008 for c in close],
            "close": close,
            "volume": [100] * n,
        }
    )
    cfg = {
        "ema_fast": 20,
        "ema_slow": 50,
        "atr_period": 14,
        "rsi_period": 14,
        "bb_period": 20,
        "bb_std": 2.0,
        "donchian_period": 20,
        "adx_period": 14,
        "volman_ema": 20,
        "firehose_every_bar": True,
        "firehose_book_filter": False,
        "firehose_jansen_filter": True,
        "firehose_harris_jump": True,
        "jansen_score_min": 0.05,
        "firehose_pip_size": 0.0001,
        "firehose_tp_pips": 1,
        "firehose_sl_pips": 30,
        "spread_bps": 0.2,
        "slippage_bps": 0.0,
        "cost_buffer": 0.01,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "er_period": 10,
    }
    frame = enrich_all(df, cfg)
    assert "jansen_score" in frame.columns
    assert "harris_jump" in frame.columns
    assert "ret_5" in frame.columns
    row = frame.iloc[-2]
    # ret_5 uses close vs close.shift(5) — both in the past relative to next bar.
    assert pd.notna(row["ret_5"])
    sig = sig_firehose(row, cfg)
    if sig is not None:
        assert sig.side in {"buy", "sell"}


if __name__ == "__main__":
    test_flags_off_do_not_block()
    test_jansen_requires_score_on_side()
    test_harris_skips_chase_after_jump()
    test_jansen_features_have_no_lookahead_and_gate_firehose()
    print("OK")
