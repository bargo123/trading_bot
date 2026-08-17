from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aegis.research.entry_signals import sig_chan_bb_fade
from aegis.research.evaluate import purged_holdout, untouched_holdout
from aegis.research.elliott import add_elliott_legs


def _times(n: int) -> pd.Series:
    return pd.date_range("2026-08-01", periods=n, freq="h", tz="UTC")


def test_purged_holdout_drops_rows_in_embargo_window():
    df = pd.DataFrame({"time": _times(100), "pnl": [0.01] * 100})
    train_plain, hold = untouched_holdout(df, holdout_frac=0.3)
    train_purged, hold2 = purged_holdout(df, holdout_frac=0.3, embargo_frac=0.05)
    assert len(hold2) == len(hold)
    assert len(train_purged) <= len(train_plain)
    assert train_purged["time"].max() < hold2["time"].min()


def test_chan_bb_fade_skips_high_impact_blackout():
    row = pd.Series(
        {
            "time": pd.Timestamp("2026-06-05 12:20:00", tz="UTC"),
            "close": 1.0900,
            "bb_lower": 1.0910,
            "bb_upper": 1.0950,
            "atr": 0.0006,
        }
    )
    events = [
        {
            "event_id": "nfp",
            "title": "US NFP",
            "currency": "USD",
            "impact": "high",
            "event_utc": pd.Timestamp("2026-06-05 12:30:00+00:00"),
            "as_of_utc": pd.Timestamp("2026-05-22 00:00:00+00:00"),
        }
    ]
    cfg = {"entry_atr_stop_mult": 1.5, "entry_rr": 2.0, "symbol": "EURUSD", "calendar_events": events}
    assert sig_chan_bb_fade(row, cfg) is None
    row2 = row.copy()
    row2["time"] = pd.Timestamp("2026-06-05 10:00:00", tz="UTC")
    assert sig_chan_bb_fade(row2, cfg) is not None


def test_chan_bb_fade_fires_outside_bands():
    row = pd.Series(
        {
            "time": pd.Timestamp("2026-08-03 10:00", tz="UTC"),
            "close": 1.0900,
            "bb_lower": 1.0910,
            "bb_upper": 1.0950,
            "atr": 0.0006,
        }
    )
    sig = sig_chan_bb_fade(row, {"entry_atr_stop_mult": 1.5, "entry_rr": 2.0})
    assert sig is not None
    assert sig.side == "buy"
    assert sig.reason == "chan_bb_fade_long"


def test_stack_votes_need_johnson_spread_ok():
    from aegis.research.six_book import stack_votes

    row = pd.Series({"johnson_spread_ok": 0.0, "struct_event": "failure_dn", "bb_pct_b": 0.0})
    assert stack_votes(row, "buy") == 0


def test_stack_votes_count_structure_and_chan():
    from aegis.research.six_book import stack_votes

    row = pd.Series(
        {
            "johnson_spread_ok": 1.0,
            "struct_event": "failure_dn",
            "bb_pct_b": 0.02,
            "close_ema_pips": 2.0,
            "ret3_pips": 1.0,
            "elliott_phase": 3,
            "elliott_up_leg": 1.0,
            "gann_cycle_hit": 1.0,
            "gann_angle_z": 0.5,
            "prado_fdiff": 0.1,
            "h1_up": 1.0,
        }
    )
    assert stack_votes(row, "buy") >= 4


def test_fractional_diff_is_finite():
    from aegis.research.prado import fractional_diff

    s = pd.Series(np.linspace(1.0, 1.1, 80))
    fd = fractional_diff(s)
    tail = fd.dropna()
    assert len(tail) > 10
    assert np.isfinite(tail.to_numpy()).all()


def test_elliott_legs_are_non_negative():
    n = 40
    closes = [1.10 + 0.0001 * i + (0.0005 if i % 7 == 0 else 0) for i in range(n)]
    highs = [c + 0.0003 for c in closes]
    lows = [c - 0.0003 for c in closes]
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-08-03", periods=n, freq="min", tz="UTC"),
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [100] * n,
        }
    )
    out = add_elliott_legs(df)
    assert (out["elliott_leg"] >= 0).all()
    assert set(out["elliott_phase"].unique()) <= {0, 1, 2, 3, 4, 5}
