from __future__ import annotations

import pandas as pd
import pytest

from aegis.research.entry_features import add_htf_direction, add_structure_columns
from aegis.research.entry_signals import ENTRY_SIGNALS, sig_failed_break, sig_structure_breakout


def _frame(highs: list[float], lows: list[float], closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    t = pd.date_range("2026-08-03 00:00", periods=n, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "time": t,
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [100] * n,
            "atr": [0.0005] * n,
        }
    )


def test_pivot_level_is_only_known_after_the_right_bar_closes():
    # bar 2 is the swing high (1.06). It must not be usable at bar 2, only from bar 3.
    highs = [1.01, 1.03, 1.06, 1.04, 1.05, 1.07, 1.06]
    lows = [1.00, 1.01, 1.03, 1.02, 1.03, 1.05, 1.04]
    closes = [1.005, 1.02, 1.05, 1.03, 1.045, 1.065, 1.05]
    out = add_structure_columns(_frame(highs, lows, closes))
    assert pd.isna(out["piv_high"].iloc[2])
    assert out["piv_high"].iloc[3] == pytest.approx(1.06)
    assert out["piv_high"].iloc[4] == pytest.approx(1.06)


def test_structure_columns_never_use_a_future_bar():
    """Recomputing on a truncated frame must give the same values for the bars kept."""
    highs = [1.0 + 0.01 * i + (0.02 if i % 5 == 0 else 0) for i in range(60)]
    lows = [h - 0.01 for h in highs]
    closes = [h - 0.004 for h in highs]
    full = add_structure_columns(_frame(highs, lows, closes))
    for cut in (20, 35, 50):
        partial = add_structure_columns(_frame(highs[:cut], lows[:cut], closes[:cut]))
        for col in ("piv_high", "piv_low", "struct_event"):
            left = full[col].iloc[:cut].reset_index(drop=True)
            right = partial[col].reset_index(drop=True)
            assert left.equals(right), f"{col} changed when future bars were added (cut={cut})"


def test_htf_direction_uses_completed_higher_timeframe_only():
    n = 400
    closes = [1.10 + 0.00002 * i for i in range(n)]
    highs = [c + 0.0002 for c in closes]
    lows = [c - 0.0002 for c in closes]
    out = add_htf_direction(_frame(highs, lows, closes))
    assert "h1_up" in out.columns
    assert "m5_up" in out.columns
    # first bar of the series has no completed H1 behind it
    assert pd.isna(out["h1_up"].iloc[0])
    later = out["h1_up"].dropna()
    assert len(later) > 0
    assert set(later.unique()) <= {0.0, 1.0}


def test_breakout_signal_needs_level_and_htf_agreement():
    row = pd.Series(
        {
            "time": pd.Timestamp("2026-08-03 10:00", tz="UTC"),
            "close": 1.1050,
            "high": 1.1055,
            "low": 1.1040,
            "atr": 0.0006,
            "piv_high": 1.1040,
            "piv_low": 1.1000,
            "struct_event": "breakout_up",
            "h1_up": 1.0,
        }
    )
    cfg = {"entry_atr_stop_mult": 1.5, "entry_rr": 2.0}
    sig = sig_structure_breakout(row, cfg)
    assert sig is not None
    assert sig.side == "buy"
    assert sig.sl < sig.entry < sig.tp
    reward = abs(sig.tp - sig.entry)
    risk = abs(sig.entry - sig.sl)
    assert reward / risk == pytest.approx(2.0, rel=1e-6)

    against = row.copy()
    against["h1_up"] = 0.0
    assert sig_structure_breakout(against, cfg) is None

    no_level = row.copy()
    no_level["piv_high"] = float("nan")
    assert sig_structure_breakout(no_level, cfg) is None


def test_failed_break_fires_opposite_the_broken_level():
    row = pd.Series(
        {
            "time": pd.Timestamp("2026-08-03 10:00", tz="UTC"),
            "close": 1.1030,
            "high": 1.1060,
            "low": 1.1025,
            "atr": 0.0006,
            "piv_high": 1.1040,
            "piv_low": 1.1000,
            "struct_event": "failure_up",
            "h1_up": 0.0,
        }
    )
    cfg = {"entry_atr_stop_mult": 1.5, "entry_rr": 2.0}
    sig = sig_failed_break(row, cfg)
    assert sig is not None
    assert sig.side == "sell"
    assert sig.tp < sig.entry < sig.sl


def test_entry_signal_registry_is_not_the_live_firehose():
    assert "firehose" not in ENTRY_SIGNALS
    assert set(ENTRY_SIGNALS) == {
        "structure_breakout",
        "failed_break",
        "level_retest",
        "chan_bb_fade",
        "chan_momentum",
        "elliott_leg3",
        "gann_turn",
        "six_book_stack",
    }


def test_entry_families_include_the_pullback_candidate_and_no_firehose():
    from aegis.research.entry_signals import entry_families

    families = entry_families()
    assert set(families) == {
        "structure_breakout",
        "failed_break",
        "level_retest",
        "chan_bb_fade",
        "chan_momentum",
        "elliott_leg3",
        "gann_turn",
        "six_book_stack",
        "pullback_retest",
    }
    for name, (prepare_fn, signal_fn) in families.items():
        assert callable(prepare_fn), name
        assert callable(signal_fn), name
