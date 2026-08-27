from __future__ import annotations

from aegis.intel.trade_controller import CANONICAL_ACTIONS, TradeController
from aegis.intel.profit_harvester import (
    HarvestInput,
    HarvestPolicy,
    HarvestPolicyEvidence,
    ProfitHarvester,
)


def _harvest_policy() -> HarvestPolicy:
    return HarvestPolicy(
        min_net_r=0.50,
        min_mfe_r=0.60,
        protected_mfe_fraction=0.60,
        max_extension_s=30.0,
        scratch_age_s=20.0,
        scratch_loss_r=-0.25,
        stalled_return_r=0.02,
        accelerating_return_r=0.05,
        evidence=HarvestPolicyEvidence(
            policy_id="validated-v1",
            status="COMPLETE",
            completed_lifecycles=12,
            oos_expectancy_after_cost=0.08,
        ),
    )


def _harvest_input(**overrides: object) -> HarvestInput:
    values: dict[str, object] = {
        "ticket": "T1",
        "side": "buy",
        "gross_pnl_r": 0.74,
        "gross_mfe_r": 0.84,
        "age_s": 10.0,
        "gross_return_5s_r": 0.05,
        "gross_return_15s_r": 0.07,
        "gross_return_30s_r": 0.09,
        "remaining_ev": 0.04,
        "remaining_ev_status": "ESTIMATED",
        "spread_normal": True,
        "observed_spread_r": 0.02,
        "observed_slippage_r": 0.01,
        "observed_commission_r": 0.01,
    }
    values.update(overrides)
    return HarvestInput(**values)


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


def test_canonical_controller_allows_green_continuation_when_harvester_supports_it():
    harvest = ProfitHarvester(_harvest_policy()).evaluate(_harvest_input(
        gross_pnl_r=0.84,
        gross_return_5s_r=0.13,
        gross_return_15s_r=0.11,
        gross_return_30s_r=0.09,
    ))
    assert harvest.action == "MOMENTUM_HOLD"

    decision = TradeController().decide(
        {"action": "HOLD", "reason": "pm_hold_justified", "why": "continuation remains supported"},
        {"action": harvest.action, "reason": harvest.reason, "why": "continuation evidence supports holding"},
        ticket="T1",
        current_mfe_r=0.84,
        profit_floor_r=0.50,
    )

    assert decision["action"] == "HOLD"
    assert "continuation" in decision["why_hold"]


def test_canonical_controller_harvests_same_green_trade_when_continuation_collapses():
    harvest = ProfitHarvester(_harvest_policy()).evaluate(_harvest_input())
    assert harvest.action == "QUICK_TAKE"

    decision = TradeController().decide(
        {"action": "HOLD", "reason": "pm_hold_justified", "why": "old target not reached"},
        {"action": harvest.action, "reason": harvest.reason, "why": "continuation collapsed"},
        ticket="T1",
        current_mfe_r=0.84,
        profit_floor_r=0.50,
    )

    assert decision["action"] == "HARVEST"
    assert decision["reason"] == "momentum_stall_profit_harvest"


def test_canonical_controller_profit_floor_ratchets_and_never_loosens():
    controller = TradeController()
    first = controller.decide(
        {"action": "HOLD"}, {"action": "LOCK", "profit_floor_r": 0.30},
        ticket="T1",
    )
    lower = controller.decide(
        {"action": "HOLD"}, {"action": "LOCK", "profit_floor_r": 0.20},
        ticket="T1",
    )
    higher = controller.decide(
        {"action": "HOLD"}, {"action": "LOCK", "profit_floor_r": 0.55},
        ticket="T1",
    )

    assert first["profit_floor_r"] == 0.30
    assert lower["profit_floor_r"] == 0.30
    assert higher["profit_floor_r"] == 0.55
