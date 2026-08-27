from __future__ import annotations

from aegis.intel.trade_controller import CANONICAL_ACTIONS, TradeController


def test_trade_controller_returns_one_canonical_harvest_action():
    decision = TradeController().decide(
        {"action": "HOLD", "reason": "pm_hold"},
        {"action": "QUICK_TAKE", "reason": "momentum_stall_profit_harvest"},
        remaining_ev=0.02,
        evidence_snapshot={"pnl_r": 0.8},
    )

    assert decision["action"] == "HARVEST"
    assert decision["action"] in CANONICAL_ACTIONS
    assert decision["why_exit"]
    assert decision["evidence_snapshot"] == {"pnl_r": 0.8}


def test_trade_controller_prioritizes_abort_over_nonterminal_evidence():
    decision = TradeController().decide(
        {"action": "EXIT", "reason": "pm_regime_change", "why": "regime invalidated"},
        {"action": "LOCK", "reason": "breakeven_lock"},
        remaining_ev=-0.01,
    )

    assert decision["action"] == "ABORT"
    assert decision["remaining_ev"] == -0.01
    assert "regime" in decision["why_exit"]


def test_trade_controller_exposes_auditable_hold_explanation():
    decision = TradeController().decide(
        {"action": "HOLD", "reason": "pm_hold_justified", "why": "pnl is progressing"},
        {"action": "HOLD", "reason": "fast_hold", "why": "momentum remains positive"},
    )

    assert decision["action"] == "HOLD"
    assert decision["why_hold"] == "pnl is progressing; momentum remains positive"
    assert decision["why_exit"] == ""


def test_replay_keeps_terminal_endpoint_distinct_from_earlier_captured_exit():
    replay = TradeController().replay_quote_path(
        quotes=[
            {"time": 0.0, "bid": 1.09999, "ask": 1.10001},
            {"time": 1.0, "bid": 1.10010, "ask": 1.10012},
            {"time": 2.0, "bid": 1.09980, "ask": 1.09982},
        ],
        side="buy",
        horizon_s=3,
        target_price=1.10005,
        stop_price=1.09993,
        pip_size=0.0001,
        slippage_price=0.00001,
        usd_per_price_unit=100000.0,
    )

    assert replay["captured_exit_action"] == "HARVEST"
    assert replay["captured_exit_net_pnl"] > 0.0
    assert replay["terminal_net_pnl"] < 0.0
