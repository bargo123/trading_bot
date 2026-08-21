"""Profit-management tests (spec B-H, I, J, O, P) incl. the deterministic
screenshot regression scenario."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.intel.profit_management import ProfitManager  # noqa: E402


class _Pos:
    def __init__(self, ticket, symbol, side, pnl, qty=0.01, price=1.10,
                 sl=0.0, comment=""):
        self.ticket = ticket
        self.symbol = symbol
        self.side = side
        self.unrealized_pnl = pnl
        self.quantity = qty
        self.avg_price = price
        self.stop_loss = sl
        self.comment = comment


def _manager(**cfg):
    return ProfitManager({"pm_mfe_arm_usd": 0.30, "pm_giveback_frac": 0.50,
                          "pm_time_decay_s": 5400, **cfg})


def test_per_ticket_mfe_is_independent():
    """Spec E: two EURUSD tickets must NEVER share one common MFE."""
    pm = _manager()
    pm.sync([_Pos("t1", "EURUSD", "sell", 0.47), _Pos("t2", "EURUSD", "sell", -0.05)])
    pm.tracks["t1"].update(pnl=0.60, now=1000.0)
    pm.tracks["t1"].update(pnl=0.47, now=1000.4)  # gave some back
    pm.tracks["t2"].update(pnl=-0.02, now=1000.5)
    assert pm.tracks["t1"].mfe_usd == pytest.approx(0.60)
    assert pm.tracks["t2"].mfe_usd == pytest.approx(0.0)
    assert pm.tracks["t1"].giveback() == pytest.approx(0.13)
    assert pm.tracks["t2"].giveback() == pytest.approx(0.0)


def test_mfe_giveback_policy_exits_after_limit():
    pm = _manager()
    pm.sync([_Pos("w", "GBPUSD", "sell", 0.98)])
    pm.tracks["w"].hypothesis_id = "exp_x"
    # MFE armed at 0.98; give back more than 50% -> EXIT.
    pm.tracks["w"].update(pnl=0.40, now=1100.0)
    v = pm.evaluate(ticket="w", volume=0.01, volume_min=0.01)
    assert v["action"] == "EXIT"
    assert v["policy"] == "mfe_giveback"
    assert "gave back" in v["why"]


def test_winner_within_giveback_gets_valid_hold_answer():
    pm = _manager()
    pm.sync([_Pos("h", "EURUSD", "sell", 0.30)])
    pm.tracks["h"].update(pnl=0.24, now=1200.0)  # gave back 20% < 50%
    v = pm.evaluate(ticket="h", volume=0.01, volume_min=0.01)
    assert v["action"] == "HOLD"
    assert "given back" in v["why"]
    # Spec FINAL: an open winner must have a real explanation.
    assert "because it has not hit the stop" not in v["why"]


def test_breakeven_lock_action_when_armed():
    pm = _manager()
    pm.sync([_Pos("l", "EURUSD", "buy", 0.35, sl=1.0950)])
    pm.tracks["l"].current_sl = 1.0950
    v = pm.evaluate(ticket="l", volume=0.01, volume_min=0.01)
    assert v["action"] == "LOCK"
    assert v["policy"] == "breakeven_lock"


def test_time_decay_exits_stale_unprogressed_trade():
    pm = _manager()
    pm.sync([_Pos("s", "USDJPY", "buy", 0.01)], now=1000.0)
    tk = pm.tracks["s"]
    tk.update(pnl=0.005, now=1000.0 + 7000)  # > time_decay_s, no progress
    v = pm.evaluate(ticket="s", volume=0.01, volume_min=0.01)
    assert v["action"] == "EXIT"
    assert v["policy"] == "time_decay"


def test_regime_change_exits_losing_position():
    pm = _manager()
    pm.sync([_Pos("r", "EURUSD", "sell", -0.10)])
    pm.tracks["r"].regime_at_open = "range"
    v = pm.evaluate(ticket="r", volume=0.01, volume_min=0.01,
                    regime_now="trend")
    assert v["action"] == "EXIT"
    assert v["policy"] == "regime_change"


def test_margin_pressure_blocks_only_nonpositive_ev():
    pm = _manager()
    pm.sync([_Pos("win", "EURUSD", "sell", 0.50), _Pos("ev0", "GBPUSD", "buy", -0.02)])
    v_win = pm.evaluate(ticket="win", volume=0.01, volume_min=0.01,
                        margin_pressure=True, remaining_ev=0.4)
    v_ev0 = pm.evaluate(ticket="ev0", volume=0.01, volume_min=0.01,
                        margin_pressure=True, remaining_ev=-0.1)
    # Never close a high-EV winner to make room; exit the non-positive EV one.
    assert v_win["action"] != "EXIT" or v_win.get("policy") != "portfolio_pressure"
    assert v_ev0["action"] == "EXIT" and v_ev0["policy"] == "portfolio_pressure"


def test_winner_to_loser_metrics_recorded_on_close():
    pm = _manager()
    pm.sync([_Pos("wl", "EURUSD", "sell", 0.45)])
    pm.tracks["wl"].update(pnl=0.50, now=1300.0)
    pm.tracks["wl"].update(pnl=-0.05, now=1400.0)  # winner became loser
    summary = pm.close_summary("wl", exit_reason="sl")
    assert pm.winner_to_loser_count == 1
    assert summary["mfe_before_close"] == pytest.approx(0.50)
    assert summary["giveback_from_mfe"] == pytest.approx(0.55)
    # Exit-learning fields present (spec G).
    assert "pl_1m" in summary and "cf_profit_at_mfe_frac_50" in summary


def test_capture_ratio_snapshot():
    pm = _manager()
    pm.sync([_Pos("c1", "EURUSD", "sell", 0.40), _Pos("c2", "GBPUSD", "sell", 0.20)])
    pm.tracks["c1"].update(pnl=0.44, now=1500.0)
    snap = pm.snapshot()
    assert snap["open_floating_profit_usd"] > 0
    assert snap["open_mfe_usd"] >= 0.64
    assert snap["profit_capture_ratio"] is not None
    for key in ("open_floating_loss_usd", "open_profit_given_back_usd",
                "winner_to_loser_count", "positions_with_profit_lock",
                "positions_without_profit_lock"):
        assert key in snap
    t = snap["tickets"][0]
    for key in ("ticket", "thesis", "hypothesis", "stage", "pnl", "mfe",
                "mae", "locked_profit", "remaining_ev", "exit_state"):
        assert key in t


# ---------------------------------------------------------------------------
# Spec I: deterministic screenshot regression scenario
# ---------------------------------------------------------------------------


def test_screenshot_regression_scenario():
    """Six tickets as in the screenshot: EURUSD SELL winners + one EURUSD BUY
    loser + GBPUSD SELL winners.

    Verified: independent thesis ownership per ticket; opposite EURUSD
    exposure is intentional/independent; margin pressure considered; MFE per
    ticket; every profitable ticket receives a valid HOLD/LOCK/EXIT decision
    with an explanation; no profitable ticket ignored.
    """
    pm = _manager()
    screenshot = [
        ("e1", "EURUSD", "sell", 0.47),
        ("e2", "EURUSD", "sell", 0.24),
        ("e3", "EURUSD", "sell", 0.15),
        ("b1", "EURUSD", "buy", -0.12),
        ("g1", "GBPUSD", "sell", 0.98),
        ("g2", "GBPUSD", "sell", 0.63),
    ]
    positions = [_Pos(t, s, sd, p) for t, s, sd, p in screenshot]
    meta = {
        "e1": {"thesis_key": "EURUSD|sell|retest|range|asia", "family": "retest"},
        "e2": {"thesis_key": "EURUSD|sell|retest|range|asia", "family": "retest"},
        "e3": {"thesis_key": "EURUSD|sell|pullback|range|asia", "family": "pullback"},
        "b1": {"thesis_key": "EURUSD|buy|breakout|range|asia", "family": "breakout"},
        "g1": {"thesis_key": "GBPUSD|sell|retest|range|asia", "family": "retest"},
        "g2": {"thesis_key": "GBPUSD|sell|momentum|range|asia", "family": "momentum"},
    }
    pm.sync(positions, meta_by_ticket=meta)

    # Independent ownership: e1/e2 share a thesis; b1 is its OWN opposite-side
    # thesis on the same symbol - intentional, not a bookkeeping accident.
    assert pm.tracks["e1"].thesis_key == pm.tracks["e2"].thesis_key
    assert pm.tracks["b1"].thesis_key != pm.tracks["e1"].thesis_key
    assert pm.tracks["b1"].side == "buy" and pm.tracks["e1"].side == "sell"

    # Per-ticket MFE: simulate favorable movement then evaluate each ticket.
    for t, mfe in (("e1", 0.55), ("e2", 0.30), ("g1", 1.05), ("g2", 0.70)):
        pm.tracks[t].update(pnl=mfe * 0.9, now=2000.0)

    decisions = {}
    for t, sym, side, p in screenshot:
        decisions[t] = pm.evaluate(
            ticket=t, volume=0.01, volume_min=0.01,
            margin_pressure=True,  # screenshot showed margin level ~157%
            remaining_ev=0.3 if p > 0 else -0.1,
        )
    # Every PROFITABLE ticket got an explicit decision with a reason.
    for t, _s, _sd, p in screenshot:
        if p > 0:
            v = decisions[t]
            assert v["action"] in {"HOLD", "LOCK", "EXIT"}, t
            assert v["why"], f"ticket {t} has no explanation"
    # The losing EURUSD BUY under margin pressure with negative EV -> EXIT.
    assert decisions["b1"]["action"] == "EXIT"
    # Winners within giveback limits remain HOLD with justification.
    assert decisions["e1"]["action"] == "HOLD"
    # Snapshot reports aggregate floating stats across ALL six tickets.
    snap = pm.snapshot()
    assert len(snap["tickets"]) == 6
    assert snap["open_floating_profit_usd"] == pytest.approx(
        sum(p for *_x, p in screenshot if p > 0), abs=0.6
    )


def test_profit_report_groups_and_point_in_time(tmp_path):
    """Spec H/M: capture stats grouped by family/symbol/exit; descriptive only."""
    from scripts.profit_report import capture_stats, main as report_main

    trades = [
        {"mfe_before_close": 0.50, "realized_pnl": 0.40, "strategy_family": "retest",
         "symbol": "EURUSD", "side": "sell", "session": "asia", "regime": "range",
         "exit_reason": "pm_mfe_giveback", "pl_5m": 0.30},
        {"mfe_before_close": 0.60, "realized_pnl": -0.05, "strategy_family": "retest",
         "symbol": "GBPUSD", "side": "sell", "session": "asia", "regime": "range",
         "exit_reason": "sl"},
        {"mfe_before_close": 0.20, "realized_pnl": 0.18, "strategy_family": "momentum",
         "symbol": "EURUSD", "side": "buy", "session": "london", "regime": "trend",
         "exit_reason": "tp"},
    ]
    overall = capture_stats(trades)
    assert overall["winner_to_loser_count"] == 1
    assert overall["sample_size"] == 3
    assert 0.0 < overall["average_profit_capture_ratio"] < 1.5
    assert overall["p25_capture_ratio"] is not None

    store = tmp_path / "exploration_experiments.json"
    store.write_text(json.dumps({"experiments": {
        "e1": {"trades": trades[:2], "strategy_family": "retest",
               "symbol": "EURUSD", "side": "sell", "session": "asia",
               "regime": "range", "status": "ACTIVE"},
    }}), encoding="utf-8")
    out = tmp_path / "profit_capture.json"
    sys.argv = ["profit_report.py", "--store", str(store), "--out", str(out)]
    assert report_main() == 0
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["overall"]["winner_to_loser_count"] == 1
    assert "by_strategy_family" in rep and "by_exit_method" in rep
    assert "point_in_time_note" in rep
