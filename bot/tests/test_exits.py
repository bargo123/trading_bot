"""Give-back lock. Not a 100% win claim."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from types import SimpleNamespace

from aegis.exits import (
    firehose_stops_from_quote,
    giveback_reason,
    mfe_after_quick_win,
    quick_win_clips,
    should_scratch_never_green,
    update_mfe,
)


def test_flags_off_never_closes():
    assert giveback_reason(0.20, -0.10, {}) is None
    assert giveback_reason(0.20, 0.0, {"close_if_gave_back": False, "lock_mfe_usd": 0.04}) is None


def test_must_have_been_green_before_lock():
    cfg = {"close_if_gave_back": True, "lock_mfe_usd": 0.04, "giveback_floor_usd": 0.0}
    assert giveback_reason(0.02, -0.01, cfg) is None
    assert giveback_reason(0.04, 0.05, cfg) is None
    assert giveback_reason(0.04, 0.0, cfg) == "gave_back"
    assert giveback_reason(0.08, -0.02, cfg) == "gave_back"


def test_fractional_giveback():
    cfg = {
        "close_if_gave_back": True,
        "lock_mfe_usd": 0.04,
        "giveback_floor_usd": -99.0,
        "giveback_frac": 0.5,
    }
    assert giveback_reason(0.10, 0.06, cfg) is None
    assert giveback_reason(0.10, 0.05, cfg) == "gave_back_frac"


def test_mfe_tracks_peak_only():
    peak = update_mfe(None, 0.01)
    peak = update_mfe(peak, 0.06)
    peak = update_mfe(peak, 0.02)
    assert peak == 0.06


def test_firehose_stops_from_live_quote_not_bar_close() -> None:
    cfg = {"firehose_tp_pips": 1, "firehose_sl_pips": 30}
    pip = 0.0001
    bid, ask = 1.10000, 1.10003
    sl, tp = firehose_stops_from_quote("buy", bid, ask, cfg, pip)
    assert abs(sl - (ask - 30 * pip)) < 1e-12
    assert abs(tp - (ask + 1 * pip)) < 1e-12
    sl2, tp2 = firehose_stops_from_quote("sell", bid, ask, cfg, pip)
    assert abs(sl2 - (bid + 30 * pip)) < 1e-12
    assert abs(tp2 - (bid - 1 * pip)) < 1e-12
    fat = firehose_stops_from_quote("buy", 1.10000, 1.10020, cfg, pip)
    assert fat is None


def test_never_green_scratch_only_when_mfe_never_armed() -> None:
    cfg = {"scratch_never_green_seconds": 300, "lock_mfe_usd": 0.02}
    assert should_scratch_never_green(held_s=400, peak=0.0, pnls=[-0.20], cfg=cfg)
    assert not should_scratch_never_green(held_s=100, peak=0.0, pnls=[-0.20], cfg=cfg)
    assert not should_scratch_never_green(held_s=400, peak=0.05, pnls=[-0.20], cfg=cfg)
    assert not should_scratch_never_green(held_s=400, peak=0.0, pnls=[-0.20, 0.01], cfg=cfg)


def test_scratch_cooldown_blocks_immediate_respray() -> None:
    from aegis.exits import should_block_scratch_cooldown

    cfg = {"scratch_cooldown_s": 120}
    assert should_block_scratch_cooldown(since_s=5.0, cfg=cfg)
    assert not should_block_scratch_cooldown(since_s=200.0, cfg=cfg)
    assert not should_block_scratch_cooldown(since_s=None, cfg=cfg)
    assert not should_block_scratch_cooldown(since_s=5.0, cfg={})


def test_quick_win_closes_winners_only() -> None:
    clips = [
        SimpleNamespace(ticket="201", unrealized_pnl=0.05),
        SimpleNamespace(ticket="202", unrealized_pnl=-0.18),
        SimpleNamespace(ticket="203", unrealized_pnl=0.049),
        SimpleNamespace(ticket="204", unrealized_pnl=0.12),
    ]
    winners = quick_win_clips(clips, 0.05)
    assert [p.ticket for p in winners] == ["201", "204"]
    left = [p.ticket for p in clips if p not in winners]
    assert left == ["202", "203"]
    assert quick_win_clips(clips, 0) == []
    assert quick_win_clips([], 0.05) == []
    assert mfe_after_quick_win([-0.18, -0.05]) == -0.05
    assert mfe_after_quick_win([]) is None
    assert giveback_reason(-0.05, -0.18, {"close_if_gave_back": True, "lock_mfe_usd": 0.02}) is None


if __name__ == "__main__":
    test_flags_off_never_closes()
    test_must_have_been_green_before_lock()
    test_fractional_giveback()
    test_mfe_tracks_peak_only()
    test_firehose_stops_from_live_quote_not_bar_close()
    test_never_green_scratch_only_when_mfe_never_armed()
    test_scratch_cooldown_blocks_immediate_respray()
    test_quick_win_closes_winners_only()
    print("OK")
