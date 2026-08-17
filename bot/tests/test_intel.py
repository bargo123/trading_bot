"""Intel meta-layer around CORE_STRATEGY_V1. Not a 100% WR claim."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.exits import working_stop
from aegis.intel.decide import intel_allows, intel_decision
from aegis.intel.frozen_v1 import frozen_payload, research_cfg
from aegis.intel.runner import first_loss_pattern, loss_removal
from aegis.intel.score import quality_score
from aegis.intel.similarity import neighbor_win_rate, similarity_allows
from aegis.session_algos import sig_firehose


def _row(**extra):
    base = {
        "open": 1.1000,
        "close": 1.1002,
        "high": 1.1003,
        "low": 1.0998,
        "ema_20": 1.0999,
        "kaufman_er": 0.5,
        "jansen_score": 0.4,
        "rsi": 58.0,
        "range_loc": 0.8,
        "brooks_in_range": False,
        "atr": 0.0004,
        "adx": 20.0,
        "harris_jump": False,
        "spread": 0.00002,
        "time": pd.Timestamp("2026-01-01 12:00", tz="UTC"),
        "close_prev": 1.1000,
        "high_prev": 1.1001,
        "low_prev": 1.0999,
    }
    base.update(extra)
    return pd.Series(base)


def test_frozen_core_disables_intel():
    payload = frozen_payload()
    assert payload["id"] == "CORE_STRATEGY_V1"
    assert payload["params"]["intel_enabled"] is False
    assert payload["params"]["firehose_every_bar"] is True
    assert float(payload["params"]["firehose_tp_pips"]) == 1
    assert float(payload["params"]["firehose_sl_pips"]) == 30
    cfg = research_cfg()
    assert cfg["intel_enabled"] is False
    assert cfg["allow_live"] is False


def test_intel_off_does_not_block_core_signal():
    row = _row()
    cfg = {
        "firehose_every_bar": True,
        "firehose_pip_size": 0.0001,
        "firehose_tp_pips": 1,
        "firehose_sl_pips": 30,
        "session_start_utc": 0,
        "session_end_utc": 24,
        "spread_bps": 0.2,
        "slippage_bps": 0.0,
        "cost_buffer": 0.01,
        "intel_enabled": False,
        "intel_quality_min": 99.0,
    }
    sig = sig_firehose(row, cfg)
    assert sig is not None
    assert sig.side == "buy"
    assert intel_allows(row, cfg, "buy")


def test_quality_and_er_filters_reject():
    row = _row(kaufman_er=0.05, jansen_score=-0.8, range_loc=0.5, brooks_in_range=True)
    cfg = {"intel_enabled": True, "intel_quality_min": 70.0, "firehose_tp_pips": 1, "firehose_pip_size": 0.0001}
    q = quality_score(row, cfg, "buy")
    assert 0.0 <= q <= 100.0
    assert intel_decision(row, cfg, "buy") == "reject"
    er_cfg = {"intel_enabled": True, "intel_min_er": 0.25}
    assert intel_decision(_row(kaufman_er=0.05), er_cfg, "buy") == "reject"
    mid = {"intel_enabled": True, "intel_skip_range_mid": True}
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.5), mid, "buy") == "wait"
    assert not intel_allows(_row(brooks_in_range=True, range_loc=0.5), mid, "buy")


def test_loss_removal_efficiency():
    base = {"wins": 100, "losses": 40}
    cand = {"wins": 97, "losses": 10}
    got = loss_removal(base, cand)
    assert got["losses_avoided"] == 30
    assert got["winners_sacrificed"] == 3
    assert got["loss_removal_efficiency"] == 10.0


def test_similarity_uses_only_memory_passed_in():
    memory = [
        {"features": {"kaufman_er": 0.5, "rsi": 55, "range_loc": 0.8, "jansen_score": 0.3, "adx": 20}, "win": True}
        for _ in range(10)
    ] + [
        {"features": {"kaufman_er": 0.05, "rsi": 50, "range_loc": 0.5, "jansen_score": 0.0, "adx": 12}, "win": False}
        for _ in range(10)
    ]
    wr = neighbor_win_rate(_row(), memory, k=8)
    assert wr is not None
    assert 0.0 <= wr <= 1.0
    assert similarity_allows(_row(), memory[:3], k=15, min_wr=0.9) is True


def test_barbwire_and_impulse_and_chop_doji_gates():
    barb = {"intel_enabled": True, "intel_skip_barbwire": True}
    assert intel_decision(_row(brooks_barbwire=True), barb, "buy") == "wait"
    assert intel_decision(_row(brooks_barbwire=False), barb, "buy") == "accept"
    against = {"intel_enabled": True, "intel_skip_impulse_against": True}
    assert intel_decision(_row(impulse_red=True), against, "buy") == "reject"
    assert intel_decision(_row(impulse_green=True), against, "sell") == "reject"
    assert intel_decision(_row(impulse_red=True), against, "sell") == "accept"
    chop = {"intel_enabled": True, "intel_skip_chop_doji": True}
    assert intel_decision(_row(volman_doji=True, kaufman_er=0.05), chop, "buy") == "wait"
    assert intel_decision(_row(volman_doji=True, kaufman_er=0.80), chop, "buy") == "accept"
    wrong = {"intel_enabled": True, "intel_skip_wrong_edge": True}
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.9), wrong, "buy") == "reject"
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.1), wrong, "sell") == "reject"
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.1), wrong, "buy") == "accept"
    extreme = {
        "intel_enabled": True,
        "intel_skip_wrong_edge": True,
        "intel_wrong_buy_loc": 0.90,
        "intel_wrong_sell_loc": 0.10,
    }
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.80), extreme, "buy") == "accept"
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.95), extreme, "buy") == "reject"
    rsi_ext = {"intel_enabled": True, "intel_skip_rsi_ext": True}
    assert intel_decision(_row(rsi=72.0), rsi_ext, "buy") == "reject"
    assert intel_decision(_row(rsi=28.0), rsi_ext, "sell") == "reject"
    assert intel_decision(_row(rsi=55.0), rsi_ext, "buy") == "accept"
    weak = {"intel_enabled": True, "intel_skip_weak_adx_edge": True, "intel_weak_adx": 22.0}
    assert (
        intel_decision(_row(brooks_in_range=True, range_loc=0.95, adx=19.0), weak, "buy")
        == "reject"
    )
    assert (
        intel_decision(_row(brooks_in_range=True, range_loc=0.02, adx=18.0), weak, "sell")
        == "reject"
    )
    assert (
        intel_decision(_row(brooks_in_range=True, range_loc=0.95, adx=40.0), weak, "buy")
        == "accept"
    )
    streak = {"intel_enabled": True, "intel_max_ema_streak": 12}
    assert intel_decision(_row(ema_side_streak=13), streak, "buy") == "reject"
    assert intel_decision(_row(ema_side_streak=8), streak, "buy") == "accept"
    fri = {"intel_enabled": True, "intel_skip_friday_hour": 15}
    friday = _row(time=pd.Timestamp("2026-08-07 16:00", tz="UTC"))
    assert intel_decision(friday, fri, "buy") == "wait"
    incomplete = {"intel_enabled": True, "intel_skip_incomplete": True}
    assert intel_decision(_row(adx=float("nan")), incomplete, "buy") == "wait"
    assert intel_decision(_row(), incomplete, "buy") == "accept"
    xd = {"intel_enabled": True, "intel_skip_extreme_doji": True}
    assert intel_decision(_row(volman_doji=True, range_loc=0.95), xd, "buy") == "reject"
    assert intel_decision(_row(volman_doji=True, range_loc=0.50), xd, "buy") == "accept"
    assert intel_decision(_row(volman_doji=False, range_loc=0.95), xd, "buy") == "accept"
    assert intel_decision(_row(volman_doji=True, range_loc=0.05), xd, "sell") == "reject"
    floor = {
        "intel_enabled": True,
        "intel_skip_floor_chop_sell": True,
        "intel_floor_chop_er": 0.05,
        "intel_floor_chop_loc": 0.15,
    }
    assert intel_decision(_row(kaufman_er=0.03, range_loc=0.0), floor, "sell") == "reject"
    assert intel_decision(_row(kaufman_er=0.03, range_loc=0.0), floor, "buy") == "accept"
    assert intel_decision(_row(kaufman_er=0.40, range_loc=0.0), floor, "sell") == "accept"
    assert intel_decision(_row(kaufman_er=0.03, range_loc=0.50), floor, "sell") == "accept"
    chase = {"intel_enabled": True, "intel_skip_late_buy_chase": True}
    assert (
        intel_decision(
            _row(rsi=68.5, range_loc=0.94, close_ema_pips=2.2), chase, "buy"
        )
        == "reject"
    )
    assert intel_decision(_row(rsi=68.5, range_loc=0.94, close_ema_pips=2.2), chase, "sell") == "accept"
    assert intel_decision(_row(rsi=55.0, range_loc=0.94, close_ema_pips=2.2), chase, "buy") == "accept"
    against = {"intel_enabled": True, "intel_skip_doji_against": True}
    assert intel_decision(_row(volman_doji=True, open=1.1002, close=1.1000), against, "buy") == "reject"
    assert intel_decision(_row(volman_doji=True, open=1.1000, close=1.1002), against, "buy") == "accept"
    assert intel_decision(_row(volman_doji=True, open=1.1000, close=1.1002), against, "sell") == "reject"
    assert intel_decision(_row(volman_doji=False, open=1.1002, close=1.1000), against, "buy") == "accept"
    ceil_d = {"intel_enabled": True, "intel_skip_ceiling_doji_buy": True}
    assert intel_decision(_row(volman_doji=True, range_loc=0.92), ceil_d, "buy") == "reject"
    assert intel_decision(_row(volman_doji=True, range_loc=0.92), ceil_d, "sell") == "accept"
    assert intel_decision(_row(volman_doji=True, range_loc=0.50), ceil_d, "buy") == "accept"
    below = {"intel_enabled": True, "intel_skip_below_range_sell": True}
    assert intel_decision(_row(range_loc=-0.07), below, "sell") == "reject"
    assert intel_decision(_row(range_loc=-0.07), below, "buy") == "accept"
    assert intel_decision(_row(range_loc=0.10), below, "sell") == "accept"
    stretch = {"intel_enabled": True, "intel_skip_stretched_doji_buy": True}
    assert (
        intel_decision(_row(volman_doji=True, range_loc=0.90, close_ema_pips=1.12), stretch, "buy")
        == "reject"
    )
    assert (
        intel_decision(_row(volman_doji=True, range_loc=0.90, close_ema_pips=1.12), stretch, "sell")
        == "accept"
    )
    assert (
        intel_decision(_row(volman_doji=True, range_loc=0.50, close_ema_pips=1.12), stretch, "buy")
        == "accept"
    )
    assert (
        intel_decision(_row(volman_doji=False, range_loc=0.90, close_ema_pips=1.12), stretch, "buy")
        == "accept"
    )
    barb_s = {"intel_enabled": True, "intel_skip_barbwire_sell": True}
    assert intel_decision(_row(brooks_barbwire=True), barb_s, "sell") == "reject"
    assert intel_decision(_row(brooks_barbwire=True), barb_s, "buy") == "accept"
    assert intel_decision(_row(brooks_barbwire=False), barb_s, "sell") == "accept"
    barb_b = {"intel_enabled": True, "intel_skip_barbwire_buy": True}
    assert intel_decision(_row(brooks_barbwire=True), barb_b, "buy") == "reject"
    assert intel_decision(_row(brooks_barbwire=True), barb_b, "sell") == "accept"
    assert intel_decision(_row(brooks_barbwire=False), barb_b, "buy") == "accept"
    stretch_s = {"intel_enabled": True, "intel_skip_stretched_sell": True}
    assert intel_decision(_row(close_ema_pips=-3.65), stretch_s, "sell") == "reject"
    assert intel_decision(_row(close_ema_pips=-3.65), stretch_s, "buy") == "accept"
    assert intel_decision(_row(close_ema_pips=-1.20), stretch_s, "sell") == "accept"
    mid_s = {"intel_enabled": True, "intel_skip_range_mid_sell": True}
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.34), mid_s, "sell") == "reject"
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.34), mid_s, "buy") == "accept"
    assert intel_decision(_row(brooks_in_range=True, range_loc=0.10), mid_s, "sell") == "accept"
    ret3s = {"intel_enabled": True, "intel_skip_ret3_chase_sell": True}
    assert intel_decision(_row(ret3_pips=-1.90), ret3s, "sell") == "reject"
    assert intel_decision(_row(ret3_pips=-1.90), ret3s, "buy") == "accept"
    assert intel_decision(_row(ret3_pips=-0.40), ret3s, "sell") == "accept"
    h12 = {"intel_enabled": True, "intel_skip_london_hour_12_sell": True}
    noon = _row(time=pd.Timestamp("2026-08-07 12:31", tz="UTC"))
    assert intel_decision(noon, h12, "sell") == "reject"
    assert intel_decision(noon, h12, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-08-07 11:00", tz="UTC")), h12, "sell") == "accept"
    above = {"intel_enabled": True, "intel_skip_above_range_buy": True}
    assert intel_decision(_row(range_loc=1.03), above, "buy") == "reject"
    assert intel_decision(_row(range_loc=1.03), above, "sell") == "accept"
    assert intel_decision(_row(range_loc=0.90), above, "buy") == "accept"
    stretch_b = {"intel_enabled": True, "intel_skip_stretched_buy": True}
    assert (
        intel_decision(_row(volman_doji=False, range_loc=1.03, close_ema_pips=1.38), stretch_b, "buy")
        == "reject"
    )
    assert (
        intel_decision(_row(volman_doji=False, range_loc=0.50, close_ema_pips=1.38), stretch_b, "buy")
        == "accept"
    )
    floor_run = {"intel_enabled": True, "intel_skip_floor_run_sell": True}
    assert intel_decision(_row(range_loc=0.12, kaufman_er=0.55), floor_run, "sell") == "reject"
    assert intel_decision(_row(range_loc=0.12, kaufman_er=0.55), floor_run, "buy") == "accept"
    assert intel_decision(_row(range_loc=0.12, kaufman_er=0.05), floor_run, "sell") == "accept"
    assert intel_decision(_row(range_loc=0.50, kaufman_er=0.55), floor_run, "sell") == "accept"
    ny19 = {"intel_enabled": True, "intel_skip_ny_hour_19_sell": True}
    h19 = _row(time=pd.Timestamp("2026-08-06 19:20", tz="UTC"))
    assert intel_decision(h19, ny19, "sell") == "reject"
    assert intel_decision(h19, ny19, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-08-06 18:00", tz="UTC")), ny19, "sell") == "accept"
    locb = {"intel_enabled": True, "intel_skip_london_open_chase_buy": True}
    open_chase = _row(
        time=pd.Timestamp("2026-08-06 09:48", tz="UTC"),
        impulse_green=True,
        ret3_pips=1.30,
    )
    assert intel_decision(open_chase, locb, "buy") == "reject"
    assert intel_decision(open_chase, locb, "sell") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-08-06 09:48", tz="UTC"), impulse_green=False, ret3_pips=1.30), locb, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-08-06 10:00", tz="UTC"), impulse_green=True, ret3_pips=1.30), locb, "buy") == "accept"
    h21 = {"intel_enabled": True, "intel_skip_hour_21_sell": True}
    t21 = _row(time=pd.Timestamp("2026-08-04 21:39", tz="UTC"))
    assert intel_decision(t21, h21, "sell") == "reject"
    assert intel_decision(t21, h21, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-08-04 20:00", tz="UTC")), h21, "sell") == "accept"
    h4 = {"intel_enabled": True, "intel_skip_asia_hour_4_sell": True}
    t4 = _row(time=pd.Timestamp("2026-08-05 04:27", tz="UTC"))
    assert intel_decision(t4, h4, "sell") == "reject"
    assert intel_decision(t4, h4, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-08-05 05:00", tz="UTC")), h4, "sell") == "accept"
    h0 = {"intel_enabled": True, "intel_skip_hour_0_dead_er_sell": True}
    t0 = _row(time=pd.Timestamp("2026-07-09 00:55", tz="UTC"), kaufman_er=0.05)
    assert intel_decision(t0, h0, "sell") == "reject"
    assert intel_decision(t0, h0, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-07-09 00:55", tz="UTC"), kaufman_er=0.40), h0, "sell") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-07-09 01:00", tz="UTC"), kaufman_er=0.05), h0, "sell") == "accept"
    h5 = {"intel_enabled": True, "intel_skip_asia_hour_5_stretch_buy": True}
    t5 = _row(time=pd.Timestamp("2026-07-07 05:02", tz="UTC"), range_loc=0.835, close_ema_pips=2.37)
    assert intel_decision(t5, h5, "buy") == "reject"
    assert intel_decision(t5, h5, "sell") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-07-10 05:54", tz="UTC"), range_loc=1.02, close_ema_pips=1.86), h5, "buy") == "accept"
    adxs = {"intel_enabled": True, "intel_skip_strong_adx_stretch_buy": True}
    assert intel_decision(_row(adx=39.5, close_ema_pips=1.38), adxs, "buy") == "reject"
    assert intel_decision(_row(adx=39.5, close_ema_pips=1.38), adxs, "sell") == "accept"
    assert intel_decision(_row(adx=20.0, close_ema_pips=1.38), adxs, "buy") == "accept"
    ceil = {"intel_enabled": True, "intel_skip_ceiling_stretch_buy": True}
    t15 = _row(range_loc=0.94, close_ema_pips=2.31, rsi=62.0, volman_doji=False)
    assert intel_decision(t15, ceil, "buy") == "reject"
    assert intel_decision(t15, ceil, "sell") == "accept"
    assert intel_decision(_row(range_loc=1.03, close_ema_pips=2.31), ceil, "buy") == "accept"
    assert intel_decision(_row(range_loc=0.94, close_ema_pips=1.20), ceil, "buy") == "accept"
    h13 = {"intel_enabled": True, "intel_skip_hour_13_dead_er_buy": True}
    t13 = _row(time=pd.Timestamp("2026-07-27 13:44", tz="UTC"), kaufman_er=0.096)
    assert intel_decision(t13, h13, "buy") == "reject"
    assert intel_decision(t13, h13, "sell") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-07-27 13:44", tz="UTC"), kaufman_er=0.40), h13, "buy") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-07-27 12:00", tz="UTC"), kaufman_er=0.096), h13, "buy") == "accept"
    h18 = {"intel_enabled": True, "intel_skip_ny_hour_18_stretch_buy": True}
    t18 = _row(time=pd.Timestamp("2026-07-14 18:10", tz="UTC"), close_ema_pips=2.94)
    assert intel_decision(t18, h18, "buy") == "reject"
    assert intel_decision(t18, h18, "sell") == "accept"
    assert intel_decision(_row(time=pd.Timestamp("2026-07-14 18:10", tz="UTC"), close_ema_pips=1.20), h18, "buy") == "accept"


def test_scratch_overlay_does_not_rewrite_core_sl_when_off():
    sl, name = working_stop("buy", 1.1000, 1.0970, {"intel_enabled": False, "intel_scratch_pips": 4})
    assert name == "sl"
    assert abs(sl - 1.0970) < 1e-12
    sl2, name2 = working_stop(
        "buy",
        1.1000,
        1.0970,
        {"intel_enabled": True, "intel_scratch_pips": 4, "firehose_pip_size": 0.0001},
    )
    assert name2 == "intel_scratch"
    assert abs(sl2 - 1.0996) < 1e-12


def test_first_loss_pattern_flags_never_green_stops():
    recs = [
        {"win": True, "pnl": 0.03, "outcome": "tp", "mfe": 0.03, "features": {"brooks_in_range": True}},
        {
            "win": False,
            "pnl": -3.0,
            "outcome": "sl",
            "mfe": 0.0,
            "side": "buy",
            "features": {"brooks_in_range": True, "brooks_barbwire": True},
        },
    ]
    got = first_loss_pattern(recs)
    assert got["n_loss"] == 1
    assert got["n_never_green_sl"] == 1
    assert got["loss_to_win_ratio"] is not None
    assert got["loss_to_win_ratio"] > 50


def test_quality_caps_wrong_extreme_and_gates_live():
    """Buy-ceiling / sell-floor in a range cannot score 80+ (loss_db pattern)."""
    ceil = _row(brooks_in_range=True, range_loc=0.96, rsi=68.0)
    floor = _row(brooks_in_range=True, range_loc=0.02, rsi=38.0)
    mid = _row(brooks_in_range=True, range_loc=0.50, rsi=52.0)
    q_ceil = quality_score(ceil, {"firehose_tp_pips": 1, "firehose_pip_size": 0.0001}, "buy")
    q_floor = quality_score(floor, {"firehose_tp_pips": 1, "firehose_pip_size": 0.0001}, "sell")
    q_mid = quality_score(mid, {"firehose_tp_pips": 1, "firehose_pip_size": 0.0001}, "buy")
    assert q_ceil <= 28.0
    assert q_floor <= 28.0
    assert q_mid > 40.0
    gate = {"intel_enabled": True, "intel_quality_min": 40.0}
    assert intel_decision(ceil, gate, "buy") == "reject"
    assert intel_decision(floor, gate, "sell") == "reject"
    assert intel_decision(mid, gate, "buy") == "accept"


if __name__ == "__main__":
    test_frozen_core_disables_intel()
    test_intel_off_does_not_block_core_signal()
    test_quality_and_er_filters_reject()
    test_loss_removal_efficiency()
    test_similarity_uses_only_memory_passed_in()
    test_barbwire_and_impulse_and_chop_doji_gates()
    test_scratch_overlay_does_not_rewrite_core_sl_when_off()
    test_first_loss_pattern_flags_never_green_stops()
    test_quality_caps_wrong_extreme_and_gates_live()
    print("OK")
