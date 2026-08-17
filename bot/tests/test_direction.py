"""Coulling / Brooks / Damir direction gates. Not a 100% accuracy claim."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.direction import direction_allows
from aegis.features import add_direction_features
from aegis.session_algos import _firehose_book_allows, sig_firehose
from aegis.strategy import prepare


def _row(**extra):
    base = {
        "high": 1.00020,
        "low": 1.00000,
        "open": 1.00000,
        "close": 1.00018,
        "volman_doji": False,
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
        "vol_sma": 100.0,
        "vpa_absorption": False,
        "vpa_no_demand": False,
        "vpa_no_supply": False,
        "structure": "chop",
        "range_loc": 0.5,
        "brooks_in_range": False,
        "brooks_failed_bo_up": False,
        "brooks_failed_bo_dn": False,
    }
    base.update(extra)
    return pd.Series(base)


def test_flags_off_do_not_censor():
    row = _row(vpa_absorption=True, brooks_in_range=True, structure="trend_down")
    assert direction_allows(row, {}, "buy")


def test_coulling_absorption_and_no_demand():
    cfg = {"firehose_vpa_filter": True}
    assert not direction_allows(_row(vpa_absorption=True), cfg, "buy")
    assert not direction_allows(_row(vpa_no_demand=True), cfg, "buy")
    assert direction_allows(_row(vpa_no_demand=True), cfg, "sell")
    assert direction_allows(_row(vpa_no_supply=True), cfg, "buy")
    assert not direction_allows(_row(vpa_no_supply=True), cfg, "sell")
    # No volume history → do not starve FX.
    assert direction_allows(_row(vol_sma=float("nan"), vpa_absorption=True), cfg, "buy")


def test_brooks_skips_mid_range_and_fades_failed_break():
    cfg = {"firehose_brooks_range": True}
    mid = _row(brooks_in_range=True, range_loc=0.50)
    assert not direction_allows(mid, cfg, "buy")
    assert not direction_allows(mid, cfg, "sell")
    bot = _row(brooks_in_range=True, range_loc=0.20)
    assert direction_allows(bot, cfg, "buy")
    assert not direction_allows(bot, cfg, "sell")
    top = _row(brooks_in_range=True, range_loc=0.80)
    assert not direction_allows(top, cfg, "buy")
    assert direction_allows(top, cfg, "sell")
    fade = _row(brooks_in_range=True, range_loc=0.50, brooks_failed_bo_dn=True)
    assert direction_allows(fade, cfg, "buy")


def test_damir_blocks_buy_into_down_structure():
    cfg = {"firehose_damir_structure": True}
    assert not direction_allows(_row(structure="trend_down"), cfg, "buy")
    assert direction_allows(_row(structure="trend_down"), cfg, "sell")
    assert not direction_allows(_row(structure="trend_up"), cfg, "sell")
    assert direction_allows(_row(structure="trend_up", range_loc=0.40), cfg, "buy")
    assert not direction_allows(_row(structure="trend_up", range_loc=0.92), cfg, "buy")
    rng = _row(structure="range", range_loc=0.50)
    assert not direction_allows(rng, cfg, "buy")
    assert not direction_allows(rng, cfg, "sell")


def test_enrich_adds_vpa_and_structure_columns():
    n = 80
    close = [1.0 + (i % 6) * 0.00004 for i in range(n)]
    df = pd.DataFrame(
        {
            "open": [c - 0.00002 for c in close],
            "high": [c + 0.00005 for c in close],
            "low": [c - 0.00005 for c in close],
            "close": close,
            "volume": [40 + (i % 7) * 30 for i in range(n)],
        }
    )
    out = add_direction_features(df, {"firehose_pip_size": 0.0001})
    for col in (
        "vpa_absorption",
        "vpa_no_demand",
        "range_loc",
        "brooks_in_range",
        "brooks_failed_bo_up",
        "structure",
    ):
        assert col in out.columns
    assert out["vpa_absorption"].dtype == bool


def test_book_filter_calls_direction_when_enabled():
    row = _row(
        vpa_absorption=True,
        vol_sma=100.0,
        kaufman_er=0.9,
    )
    cfg = {
        "firehose_book_filter": True,
        "firehose_vpa_filter": True,
        "firehose_chart_read": False,
        "firehose_skip_doji": False,
        "firehose_require_body": False,
        "firehose_min_er": 0.0,
        "firehose_min_range_pips": 0.0,
        "firehose_pip_size": 0.0001,
    }
    assert not _firehose_book_allows(row, cfg, "buy")
    row["vpa_absorption"] = False
    assert _firehose_book_allows(row, cfg, "buy")


def test_trending_firehose_still_fires_with_direction_flags():
    n = 80
    close = [1.0 + i * 0.00015 for i in range(n)]
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC"),
            "open": [c - 0.00012 for c in close],
            "high": [c + 0.00002 for c in close],
            "low": [c - 0.00014 for c in close],
            "close": close,
            "volume": [80 + i for i in range(n)],
        }
    )
    cfg = {
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
        "firehose_chart_read": False,
        "firehose_skip_doji": False,
        "firehose_require_body": False,
        "firehose_min_er": 0.0,
        "firehose_min_range_pips": 0.0,
        "firehose_vpa_filter": True,
        "firehose_brooks_range": True,
        "firehose_damir_structure": True,
        "spread_bps": 0.2,
        "slippage_bps": 0.0,
        "cost_buffer": 1.0,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "er_period": 10,
        "htf_ema_period": 20,
        "signal_mode": "firehose",
    }
    frame = prepare(df, cfg)
    sig = sig_firehose(frame.iloc[-2], cfg)
    assert sig is not None
    assert sig.side == "buy"


if __name__ == "__main__":
    test_flags_off_do_not_censor()
    test_coulling_absorption_and_no_demand()
    test_brooks_skips_mid_range_and_fades_failed_break()
    test_damir_blocks_buy_into_down_structure()
    test_enrich_adds_vpa_and_structure_columns()
    test_book_filter_calls_direction_when_enabled()
    test_trending_firehose_still_fires_with_direction_flags()
    print("OK")
