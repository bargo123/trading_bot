from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from aegis.intel.fast_firehose import FastExitConfig, FastExitStateMachine
from aegis.intel.opportunity_engine import rank_and_allocate
from aegis.intel.outcome_memory import classify_lifecycle
from aegis.intel.profit_harvester import HarvestInput, HarvestPolicy, HarvestPolicyEvidence, ProfitHarvester
from aegis.intel.trade_economics import evaluate_trade_economics
from aegis.intel.trade_controller import TradeController
from aegis.research.short_horizon_artifact import build_quote_training_frame


def _policy() -> HarvestPolicy:
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
            policy_id="mission-policy",
            status="COMPLETE",
            completed_lifecycles=100,
            oos_expectancy_after_cost=0.01,
        ),
    )


def test_expected_opening_spread_does_not_trigger_fast_loser_scratch():
    result = FastExitStateMachine(FastExitConfig()).evaluate(
        side="buy",
        entry_price=1.10000,
        current_mark=1.09990,
        stop_loss=1.09960,
        target=1.10060,
        opened_ts=100.0,
        now=100.1,
        pnl_pips=-1.0,
        mfe_pips=0.0,
        mae_pips=-1.0,
        stop_pips=4.0,
        pip=0.0001,
        expected_initial_friction_pips=1.0,
    )

    assert result["action"] == "HOLD"
    assert result["adverse_excursion_beyond_expected_friction_pips"] == pytest.approx(0.0)


def test_adverse_movement_beyond_expected_friction_can_abort_immediately():
    result = FastExitStateMachine(FastExitConfig()).evaluate(
        side="buy",
        entry_price=1.10000,
        current_mark=1.09965,
        stop_loss=1.09960,
        target=1.10060,
        opened_ts=100.0,
        now=100.01,
        pnl_pips=-3.5,
        mfe_pips=0.0,
        mae_pips=-3.5,
        stop_pips=4.0,
        pip=0.0001,
        expected_initial_friction_pips=1.0,
    )

    assert result["action"] == "SCRATCH"
    assert result["reason"] == "loss_fraction_scratch"
    assert result["adverse_excursion_beyond_expected_friction_pips"] == pytest.approx(2.5)


def test_no_progress_horizon_does_not_require_arbitrary_minimum_hold():
    result = FastExitStateMachine(FastExitConfig()).evaluate(
        side="sell",
        entry_price=1.10000,
        current_mark=1.10040,
        stop_loss=1.10050,
        target=1.09940,
        opened_ts=100.0,
        now=100.001,
        pnl_pips=-4.0,
        mfe_pips=0.0,
        mae_pips=-4.0,
        stop_pips=10.0,
        pip=0.0001,
        expected_initial_friction_pips=0.5,
    )
    assert result["action"] == "SCRATCH"


def test_normal_opening_friction_is_not_fast_loser_evidence():
    result = classify_lifecycle(
        realized_net_usd=-0.03,
        mfe_usd=0.0,
        mae_usd=-0.03,
        time_to_green_s=None,
        selected_horizon_s=5,
        expected_initial_friction_usd=0.03,
    )
    assert result["speed_label"] is None
    assert result["classification"] == "AMBIGUOUS"


def test_harvester_does_not_scratch_for_expected_opening_spread_only():
    observed = HarvestInput(
        ticket="T1",
        side="buy",
        gross_pnl_r=-0.20,
        gross_mfe_r=0.0,
        age_s=1.0,
        gross_return_5s_r=-0.01,
        gross_return_15s_r=0.0,
        gross_return_30s_r=0.0,
        remaining_ev=0.10,
        remaining_ev_status="ESTIMATED",
        spread_normal=True,
        observed_spread_r=0.20,
        observed_slippage_r=0.0,
        observed_commission_r=0.0,
        expected_initial_friction_r=0.20,
    )
    assert ProfitHarvester(_policy()).evaluate(observed).action == "UNAVAILABLE"


def test_untrusted_probability_cannot_be_passed_as_supplied_authority():
    result = evaluate_trade_economics(
        side="buy",
        entry=1.1000,
        invalidation=1.0990,
        target=1.1020,
        lots=0.01,
        spec={"trade_tick_size": 0.00001, "trade_tick_value": 1.0},
        spread_price=0.00001,
        p_win=0.99,
        probability_provenance="research_proxy",
    )
    assert not result.acceptable
    assert result.reason == "probability_provenance_untrusted"


def test_m1_structural_probability_cannot_masquerade_as_seconds_capture():
    from aegis.intel.analogue_store import AnalogueStore

    store = AnalogueStore(
        [{
            "bar_time": "2026-01-01T00:00:00Z",
            "symbol": "EURUSD",
            "side": "buy",
            "regime": "trend",
            "structure": "breakout",
            "session": "london",
            "outcome": 1.0,
            "horizon_s": 60,
        }],
        provenance="mt5_m1",
        outcome_unit="usd",
    )
    evidence = store.query(
        signature={"symbol": "EURUSD", "side": "buy", "regime": "trend", "structure": "breakout", "session": "london"},
        before_time="2026-01-01T00:01:00Z",
        min_n=1,
        min_similarity=0.0,
        horizon_s=3,
    )
    assert evidence.analogue_n == 0
    assert evidence.horizon_s == 3


def test_research_replay_and_controller_use_same_sequential_actions():
    quotes = [
        {"time": 0.0, "bid": 1.09999, "ask": 1.10001},
        {"time": 1.0, "bid": 1.10002, "ask": 1.10004},
        {"time": 2.0, "bid": 1.10010, "ask": 1.10012},
    ]
    replay = TradeController().replay_quote_path(
        quotes=quotes,
        side="buy",
        horizon_s=3,
        target_price=1.10005,
        stop_price=1.09993,
    )
    assert replay["status"] == "REPLAYED"
    assert replay["captured_exit_reason"] == "harvest"
    assert replay["actions"][0]["action"] == "HOLD"
    assert replay["actions"][1]["action"] == "HARVEST"


def test_true_training_frame_matches_shared_replay_and_executable_sides():
    times = pd.date_range("2026-01-01T00:00:00Z", periods=12, freq="1s")
    mid = np.full(12, 1.1)
    mid[1:] = 1.10010
    frame = build_quote_training_frame(
        {"EURUSD": pd.DataFrame({"time": times, "bid": mid - 0.00001, "ask": mid + 0.00001})},
        horizons=(3,),
        sample_every_s=3,
        target_mode="captured_exit_replay",
    )
    row = frame[(frame["time"] == times[0]) & (frame["side"] == "buy")].iloc[0]
    assert row["entry_price"] == pytest.approx(1.10001)
    # BUY enters at ASK and exits at BID; the opening spread is charged once.
    assert row["captured_exit_net_pnl"] == pytest.approx(0.00008)
    assert row["captured_exit_reason"] == "harvest"


def test_win_rate_first_ranking_uses_capture_lcb_before_raw_ev():
    def candidate(name, lcb, p, ev):
        return {
            "candidate_id": name,
            "thesis_key": name,
            "p_captured_win": p,
            "p_captured_win_lcb95": lcb,
            "expected_net_ev": ev,
            "portfolio_ok": True,
        }

    ranked, _ = rank_and_allocate(
        [candidate("big-ev", 0.80, 0.99, 10.0), candidate("supported", 0.90, 0.93, 0.10)],
        max_positions=1,
    )
    assert ranked[0]["candidate_id"] == "supported"


def test_order_request_can_separate_virtual_strategy_geometry_from_broker_stop():
    from aegis.engines.base import OrderRequest

    req = OrderRequest(
        symbol="EURUSD",
        side="buy",
        quantity=0.01,
        stop_loss=1.0990,
        take_profit=1.1020,
        broker_stop_loss=1.0980,
        broker_take_profit=None,
    )
    assert req.stop_loss == pytest.approx(1.0990)
    assert req.broker_stop_loss == pytest.approx(1.0980)
    assert req.broker_take_profit is None
