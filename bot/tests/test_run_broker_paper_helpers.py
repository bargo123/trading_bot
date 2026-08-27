from __future__ import annotations

import pandas as pd
import pytest

from aegis.engines.base import PositionSnapshot, Quote
from aegis.intel.firehose_basket import BasketMetadataStore
from aegis.intel.firehose_turnover import FirehoseReentryGuard, TurnoverMetrics
from aegis.intel.ticket_metadata import TicketMetadataStore, create_ticket_metadata
from aegis.sizing import ContractSpec
from scripts.run_broker_paper import (
    confirmed_position_geometry,
    ticket_metadata_from_pending,
    close_ticket_confirmed,
    broker_close_evidence,
    exploration_order_risk_check,
    firehose_lifecycle_identity,
    firehose_funnel_risk_row,
    record_funnel_execution,
    merge_firehose_funnel_counts,
    normalize_protective_stops,
    emergency_broker_stop,
    reprice_frozen_virtual_geometry,
    validate_virtual_strategy_geometry,
    resize_order_quantity_to_risk,
    _write_text_atomically,
    order_margin_for_send,
    persist_confirmed_firehose_basket,
    record_confirmed_firehose_open,
    reconcile_confirmed_firehose_basket_cleanups,
    remove_confirmed_firehose_basket,
    remove_confirmed_firehose_basket_then_cleanup,
    firehose_decision_snapshot,
    frozen_opportunity_from_decision,
    intelligent_refresh_spread_limit,
    meaningful_quote_change,
    quote_scan_verdict,
    acquire_fresh_quote,
    QuoteFeedHealth,
    video_style_signal_for_scan,
    pending_order_lifecycle_metadata,
    outcome_features_from_ticket_metadata,
    record_broker_confirmed_outcome_learning,
    legacy_normal_exit_enabled,
)
from aegis.intel.send_guard import candidate_spread_limit, refresh_verdict


def test_heartbeat_atomic_writer_replaces_target_without_temp_file(tmp_path):
    target = tmp_path / "bot_heartbeat.json"
    target.write_text("old", encoding="utf-8")

    _write_text_atomically(target, '{"status":"running"}')

    assert target.read_text(encoding="utf-8") == '{"status":"running"}'
    assert list(tmp_path.glob(".bot_heartbeat.json.*.tmp")) == []


def test_intelligent_firehose_has_only_trade_controller_normal_exit_authority():
    assert legacy_normal_exit_enabled(False) is True
    assert legacy_normal_exit_enabled(True) is False


def test_meaningful_quote_change_allows_same_bar_reevaluation():
    previous = {"bid": 1.10000, "ask": 1.10002}
    assert meaningful_quote_change(previous, bid=1.10000, ask=1.10002, pip=0.0001) is False
    assert meaningful_quote_change(previous, bid=1.10001, ask=1.10003, pip=0.0001) is True
    assert meaningful_quote_change(None, bid=1.1, ask=1.1001, pip=0.0001) is True


def test_stale_quote_is_research_usable_but_not_executable():
    now = pd.Timestamp("2026-08-28T00:00:00Z").to_pydatetime()
    quote = Quote(
        symbol="EURUSD", bid=1.10000, ask=1.10002,
        time=now - pd.Timedelta(seconds=7),
    )

    verdict = quote_scan_verdict(quote, max_age_s=5.0, max_future_skew_s=5.0, now=now)

    assert verdict.scan_allowed is True
    assert verdict.execution_allowed is False
    assert verdict.reason == "stale_for_execution"


def test_fresh_quote_acquisition_polls_without_rerunning_research():
    class Clock:
        wall = 100.0
        mono = 0.0

        def monotonic(self):
            return self.mono

        def sleep(self, seconds):
            self.mono += seconds

    clock = Clock()
    quotes = iter([
        Quote("EURUSD", 1.10000, 1.10002, pd.Timestamp(93, unit="s", tz="UTC").to_pydatetime()),
        Quote("EURUSD", 1.10001, 1.10003, pd.Timestamp(99.5, unit="s", tz="UTC").to_pydatetime()),
    ])
    initial = Quote("EURUSD", 1.10000, 1.10002, pd.Timestamp(93, unit="s", tz="UTC").to_pydatetime())

    acquired, detail = acquire_fresh_quote(
        lambda: next(quotes),
        initial_quote=initial,
        max_age_s=5.0,
        max_future_skew_s=5.0,
        timeout_s=0.5,
        poll_s=0.05,
        now_fn=lambda: clock.wall,
        monotonic_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    assert acquired is not None
    assert acquired.bid == 1.10001
    assert detail["attempts"] == 2
    assert detail["acquired"] is True


def test_feed_health_distinguishes_benchmark_stall_from_normal_advancement():
    health = QuoteFeedHealth.for_symbols(["EURUSD", "GBPUSD", "USDJPY"])
    quote = Quote("EURUSD", 1.1, 1.1001, pd.Timestamp(100, unit="s", tz="UTC").to_pydatetime())
    for symbol in health.benchmarks:
        health.observe(symbol, quote, 0.0)

    assert health.evaluate(0.0, stall_after_s=30.0) == "HEALTHY"
    assert health.evaluate(31.0, stall_after_s=30.0) == "FEED_STALLED"
    assert health.stall_count == 1

    advanced = Quote("EURUSD", 1.10001, 1.10011, pd.Timestamp(131, unit="s", tz="UTC").to_pydatetime())
    health.observe("EURUSD", advanced, 31.0)
    assert health.evaluate(31.0, stall_after_s=30.0) == "HEALTHY"


def test_emergency_broker_stop_is_wide_but_stays_inside_risk_budget():
    spec = {
        "name": "EURUSD",
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "volume_max": 100.0,
        "point": 0.00001,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "trade_contract_size": 100000.0,
    }
    stop = emergency_broker_stop(
        symbol="EURUSD", side="buy", entry=1.10000,
        virtual_stop=1.09998, quantity=0.01, spec=spec,
        max_risk_usd=0.15,
    )
    assert stop == pytest.approx(1.09992)
    assert emergency_broker_stop(
        symbol="EURUSD", side="buy", entry=1.10000,
        virtual_stop=1.09990, quantity=0.01, spec=spec,
        max_risk_usd=0.15,
    ) is None


def test_forced_demo_emergency_stop_clamps_to_existing_risk_budget():
    spec = {
        "name": "EURUSD",
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "point": 0.00001,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "trade_contract_size": 100000.0,
    }

    stop = emergency_broker_stop(
        symbol="EURUSD", side="buy", entry=1.10000,
        virtual_stop=1.09990, quantity=0.01, spec=spec,
        max_risk_usd=0.15, clamp_to_risk=True,
    )

    assert stop == pytest.approx(1.09985)


def test_emergency_broker_stop_clears_the_executable_liquidation_side():
    spec = {
        "name": "EURUSD",
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "volume_min": 0.01,
        "volume_step": 0.01,
        "volume_max": 100.0,
        "point": 0.00001,
        "trade_stops_level": 0,
        "trade_freeze_level": 0,
        "trade_contract_size": 100000.0,
    }

    buy_stop = emergency_broker_stop(
        symbol="EURUSD", side="buy", entry=1.10020,
        virtual_stop=1.10019, quantity=0.01, spec=spec,
        max_risk_usd=0.30, clamp_to_risk=True,
        market_bid=1.10000, market_ask=1.10020,
    )
    sell_stop = emergency_broker_stop(
        symbol="EURUSD", side="sell", entry=1.10000,
        virtual_stop=1.10001, quantity=0.01, spec=spec,
        max_risk_usd=0.30, clamp_to_risk=True,
        market_bid=1.10000, market_ask=1.10020,
    )

    assert buy_stop is not None and buy_stop < 1.10000
    assert sell_stop is not None and sell_stop > 1.10020


def test_frozen_virtual_geometry_reprices_same_identity_on_fresh_quote():
    repriced = reprice_frozen_virtual_geometry(
        side="buy",
        discovery_entry=1.10020,
        discovery_stop=1.09990,
        discovery_target=1.10070,
        fresh_entry=1.10035,
    )

    assert repriced == pytest.approx((1.10005, 1.10085))
    assert validate_virtual_strategy_geometry(
        side="buy", entry=1.10035, stop=repriced[0], target=repriced[1]
    ) == (True, "")


def test_virtual_geometry_validation_does_not_apply_broker_minimum_distance():
    ok, reason = validate_virtual_strategy_geometry(
        side="sell", entry=1.10000, stop=1.10002, target=1.09999
    )
    assert ok, reason


def test_risk_revalidation_resizes_down_to_broker_step():
    assert resize_order_quantity_to_risk(
        requested_quantity=0.03,
        max_lots=0.02,
        volume_min=0.01,
        volume_step=0.01,
    ) == pytest.approx(0.02)


def test_risk_revalidation_rejects_when_minimum_lot_still_exceeds_budget():
    assert resize_order_quantity_to_risk(
        requested_quantity=0.03,
        max_lots=0.005,
        volume_min=0.01,
        volume_step=0.01,
    ) is None


def test_frozen_opportunity_preserves_the_decision_identity():
    from aegis.intel.firehose_brain import DemoDecision

    decision = DemoDecision(
        "fire",
        "exploration_hypothesis_test",
        side="sell",
        sl=1.1010,
        tp=1.0990,
        quantity=0.01,
        expected_net_value=0.12,
        journal={
            "exploration": True,
            "hypothesis_id": "h1",
            "thesis_key": "EURUSD|sell|breakout|range|asia",
            "setup_family": "breakout",
            "variant_id": "breakout:sell:5s",
            "search_horizon_s": 5,
            "capture_authorization": {
                "probability": 0.63,
                "lower_95": 0.56,
                "required_probability": 0.50,
                "observations": 100,
            },
            "exploration_economics": {"econ_expected_net_usd": 0.12},
        },
    )

    frozen = frozen_opportunity_from_decision(
        decision=decision,
        symbol="EURUSD",
        scan_id="scan-1",
        bar_time="2026-08-27T00:00:00+00:00",
        bid=1.1000,
        ask=1.1002,
        stop=1.1010,
        target=1.0990,
        quantity=0.01,
    )

    assert frozen["candidate_id"] == "scan-1:breakout:sell:5s"
    assert frozen["side"] == "sell"
    assert frozen["mechanism"] == "breakout"
    assert frozen["horizon_s"] == 5
    assert frozen["stop"] == 1.1010
    assert frozen["target"] == 1.0990
    assert frozen["authority_probability"] == 0.63
    assert frozen["shadow_model_probability"] is None


def test_validated_frozen_opportunity_enters_global_pool_with_model_probability():
    from aegis.intel.firehose_brain import DemoDecision
    from aegis.intel.opportunity_engine import rank_and_allocate

    decision = DemoDecision(
        "fire", "positive_state_ev_on_validated_strategy", side="buy",
        sl=1.0990, tp=1.1010, quantity=0.01, expected_net_value=0.12,
        journal={
            "exploration": False,
            "setup_family": "validated_breakout",
            "variant_id": "validated_breakout:buy:5s",
            "short_horizon_prediction": {
                "probability": 0.82,
                "p_captured_win_lcb95": 0.61,
                "expected_net_pnl": 0.12,
                "decision_horizon_s": 5,
            },
        },
    )

    frozen = frozen_opportunity_from_decision(
        decision=decision, symbol="EURUSD", scan_id="scan-v", bar_time="t-v",
        bid=1.1000, ask=1.1002, stop=1.0990, target=1.1010, quantity=0.01,
    )
    ranked, selected = rank_and_allocate([frozen], max_positions=1)

    assert len(ranked) == 1
    assert selected[0] is ranked[0]
    assert selected[0]["lane"] == "validated"
    assert selected[0]["p_captured_win"] == 0.82
    assert selected[0]["p_captured_win_lcb95"] == 0.61
    assert selected[0]["side"] == "buy"
    assert selected[0]["horizon_s"] == 5


def test_forced_demo_frozen_opportunity_reaches_global_allocator_without_p_capture():
    from aegis.intel.firehose_brain import DemoDecision
    from aegis.intel.opportunity_engine import rank_and_allocate

    decision = DemoDecision(
        "fire", "exploration_hypothesis_test", side="buy",
        sl=1.0999, tp=1.1007, quantity=0.01, expected_net_value=None,
        journal={
            "exploration": True,
            "exploration_lane": "FORCED_DEMO_EXPLORATION",
            "authority_type": "FORCED_DEMO_EXPLORATION",
            "calibration_status": "UNCALIBRATED",
            "selection_score": 0.42,
            "selection_score_type": "forced_demo_comparative",
            "setup_family": "forced_test",
            "variant_id": "forced_test:buy:3s",
            "search_horizon_s": 3,
            "capture_authorization": {
                "probability": None, "lower_95": None,
                "observations": 0, "evidence_source": "forced_demo_exploration",
            },
            "exploration_economics": {
                "econ_expected_net_usd": None,
                "econ_expected_loss_usd": 0.10,
            },
        },
    )

    frozen = frozen_opportunity_from_decision(
        decision=decision, symbol="EURUSD", scan_id="scan-f",
        bar_time="2026-08-27T00:00:00+00:00", bid=1.1000, ask=1.1002,
        stop=1.0999, target=1.1007, quantity=0.01,
    )
    ranked, selected = rank_and_allocate([frozen], max_positions=1)

    assert len(ranked) == 1
    assert selected[0] is ranked[0]
    assert selected[0]["lane"] == "FORCED_DEMO_EXPLORATION"
    assert selected[0]["p_captured_win"] is None
    assert selected[0]["authority_type"] == "FORCED_DEMO_EXPLORATION"
    assert selected[0]["selection_score"] == 0.42


def test_risk_halt_records_one_terminal_funnel_row_without_order_intent():
    row = firehose_funnel_risk_row(
        scan_id="scan_123",
        symbol="EURUSD",
        bar="2026-08-25T09:00:00+00:00",
        reason="daily_loss 10.11%",
    )

    assert row == {
        "event": "firehose_funnel.v1",
        "scan_id": "scan_123",
        "symbol": "EURUSD",
        "bar": "2026-08-25T09:00:00+00:00",
        "terminal": "RISK_REJECT",
        "micro_candidate_count": 0,
        "book_supported": False,
        "validated_match": False,
        "exploration_eligible": False,
        "brain_intent": False,
        "submitted": False,
        "filled": False,
        "reason": "daily_loss 10.11%",
    }


def test_merge_firehose_funnel_counts_preserves_observed_halted_scans():
    merged = merge_firehose_funnel_counts(
        {"SCANS": 0, "scans": 7, "RISK_REJECT": 0, "FIRES": 2},
        {"SCANS": 3, "RISK_REJECT": 3},
    )

    assert merged == {"SCANS": 7, "RISK_REJECT": 3, "FIRES": 2}


def test_record_funnel_execution_counts_only_real_submission_and_fill():
    counts = {"FIRES": 0, "FILLS": 0}

    record_funnel_execution(counts, submitted=True, filled=False)
    record_funnel_execution(counts, submitted=True, filled=True)

    assert counts == {"FIRES": 2, "FILLS": 1}


def test_confirmed_ticket_metadata_preserves_entry_ev_for_remaining_ev_policy():
    metadata = create_ticket_metadata(
        ticket="T_EV",
        hypothesis_id="hyp-ev",
        thesis_key="thesis-ev",
        strategy_family="micro",
        expected_mechanism="continuation",
        side="buy",
        entry_price=1.1000,
        stop_loss=1.0990,
        target_price=1.1020,
        max_hold_s=45,
        regime="trend",
        session="london",
        entry_ev=0.12,
        decision_snapshot={"why": "WHY_BUY", "ranking": ["buy"]},
    )

    restored = type(metadata).from_dict(metadata.to_dict())

    assert restored.entry_ev == 0.12
    assert restored.decision_snapshot == {"why": "WHY_BUY", "ranking": ["buy"]}


def test_pending_ticket_metadata_survives_restart_before_fill(tmp_path):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    assert store.begin_pending_order(
        "EXP-hyp-1",
        {
            "hypothesis_id": "hyp-1",
            "symbol": "EURUSD",
            "side": "buy",
            "selected_horizon_s": 5,
            "entry_price": 1.1,
        },
    )

    restarted = TicketMetadataStore(tmp_path / "tickets.json")
    assert restarted.pending_order("EXP-hyp-1") == {
        "hypothesis_id": "hyp-1",
        "symbol": "EURUSD",
        "side": "buy",
        "selected_horizon_s": 5,
        "entry_price": 1.1,
    }


def test_pending_ticket_metadata_is_rebound_to_broker_ticket_after_restart():
    metadata = ticket_metadata_from_pending(
        ticket="T-RESTORED",
        pending={
            "hypothesis_id": "hyp-1",
            "thesis_key": "EURUSD|buy|micro|trend|london",
            "strategy_family": "micro",
            "expected_mechanism": "continuation",
            "side": "buy",
            "target_price": 1.102,
            "max_hold_s": 5,
            "selected_horizon_s": 5,
            "regime": "trend",
            "session": "london",
            "information_id": "info-1",
            "model_artifact": {"status": "SHADOW_ONLY"},
            "prediction_snapshot": {"probability": 0.8},
            "p_captured_win": 0.8,
            "decision_snapshot": {"why": "WHY_BUY"},
        },
        position=PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.1002,
            stop_loss=1.0992, ticket="T-RESTORED",
        ),
    )

    assert metadata is not None
    assert metadata.ticket == "T-RESTORED"
    assert metadata.entry_price == pytest.approx(1.1002)
    assert metadata.stop_loss == pytest.approx(1.0992)
    assert metadata.selected_horizon_s == 5
    assert metadata.prediction_snapshot == {"probability": 0.8}


def test_pending_metadata_keeps_exploration_authority_separate_from_shadow_probability():
    from aegis.intel.firehose_brain import DemoDecision

    decision = DemoDecision(
        "fire", "exploration_hypothesis_test", side="buy", expected_net_value=0.07,
        journal={
            "exploration": True,
            "hypothesis_id": "h-exp",
            "thesis_key": "EURUSD|buy|breakout|range|asia",
            "setup_family": "breakout",
            "search_horizon_s": 5,
            "capture_authorization": {
                "probability": 0.41,
                "lower_95": 0.38,
                "required_probability": 0.35,
                "observations": 80,
                "evidence_source": "measured_analogue_capture",
            },
            "shadow_model_probability": 0.91,
            "exploration_economics": {
                "econ_expected_net_usd": 0.07,
                "econ_expected_loss_usd": 0.15,
            },
        },
    )
    pending = pending_order_lifecycle_metadata(
        decision=decision,
        snapshot={
            "prediction": {"probability": 0.91, "expected_net_pnl": 0.9},
            "model": {"status": "SHADOW_ONLY"},
            "economics": {},
            "risk": {"spread": 0.0001},
        },
        symbol="EURUSD", side="buy", entry=1.1, stop=1.099, target=1.102,
        client_tag="EXP-h-exp", config={"commission_round_trip_usd": 0.0},
    )

    assert pending["entry_ev"] == pytest.approx(0.07)
    assert pending["authority_probability"] == pytest.approx(0.41)
    assert pending["p_captured_win"] == pytest.approx(0.41)
    assert pending["shadow_model_probability"] == pytest.approx(0.91)
    assert pending["expected_net_pnl"] == pytest.approx(0.07)


def test_outcome_learning_helper_keeps_exact_pre_entry_snapshot_and_broker_net_truth(tmp_path):
    from aegis.intel.outcome_memory import OutcomeMemoryStore

    metadata = create_ticket_metadata(
        ticket="T-LEARN",
        hypothesis_id="hyp-learn",
        thesis_key="thesis-learn",
        strategy_family="breakout",
        expected_mechanism="micro_momentum",
        side="buy",
        entry_price=1.1002,
        stop_loss=1.0990,
        target_price=1.1020,
        max_hold_s=5,
        regime="trend",
        session="london",
        symbol="EURUSD",
        selected_horizon_s=5,
        feature_snapshot={"return_3s": 0.0003, "m5": {"direction": "up"}},
        prediction_snapshot={"probability": 0.62},
        p_captured_win=0.62,
        entry_ev=0.04,
        entry_geometry={"entry_price": 1.1002, "stop_loss": 1.0990},
        cost_evidence={"spread_price": 0.0002},
        spread_assumption=0.0002,
        commission_assumption=0.01,
    )
    state = outcome_features_from_ticket_metadata(metadata)
    assert state["return_3s"] == pytest.approx(0.0003)
    assert state["short_returns"]["return_3s"] == pytest.approx(0.0003)
    assert state["m5_context"]["m5"]["direction"] == "up"
    assert state["mechanism"] == "micro_momentum"
    assert state["entry_geometry"]["stop_loss"] == pytest.approx(1.0990)
    assert state["p_captured_win"] == pytest.approx(0.62)

    store = OutcomeMemoryStore(tmp_path / "outcome_memory.json")
    row = record_broker_confirmed_outcome_learning(
        outcome_memory=store,
        outcome_id="T-LEARN",
        close_facts={
            "status": "BROKER_CONFIRMED", "confirmed": True,
            "realized_net_usd": -0.08, "cost_usd": 0.03,
            "close_timestamp": "2026-08-27T10:00:02Z",
        },
        metadata=metadata,
        lifecycle_detail={"mfe_usd": 0.01, "mae_usd": -0.10, "first_green_s": None},
    )
    assert row["evidence_status"] == "BROKER_CONFIRMED"
    assert row["realized_net_usd"] == pytest.approx(-0.08)
    assert row["pre_entry_state"]["return_3s"] == pytest.approx(0.0003)


def test_outcome_learning_helper_stages_context_until_delayed_deal_confirmation(tmp_path):
    from aegis.intel.outcome_memory import OutcomeMemoryStore

    path = tmp_path / "outcome_memory.json"
    store = OutcomeMemoryStore(path)
    metadata = _ticket_metadata(basket_id=None)
    pending = record_broker_confirmed_outcome_learning(
        outcome_memory=store,
        outcome_id="T-DELAYED",
        close_facts={"status": "INCOMPLETE_BROKER_EVIDENCE"},
        metadata=metadata,
        lifecycle_detail={"mfe_usd": 0.01, "mae_usd": -0.05, "first_green_s": None},
    )
    assert pending["status"] == "PENDING"

    restarted = OutcomeMemoryStore(path)
    confirmed = record_broker_confirmed_outcome_learning(
        outcome_memory=restarted,
        outcome_id="T-DELAYED",
        close_facts={
            "status": "BROKER_CONFIRMED", "confirmed": True,
            "realized_net_usd": -0.08, "cost_usd": 0.02,
            "close_timestamp": "2026-08-27T10:00:02Z",
        },
        metadata=None,
        lifecycle_detail={},
    )
    assert confirmed["evidence_status"] == "BROKER_CONFIRMED"
    assert confirmed["pre_entry_state"]["symbol"] == "EURUSD"


def test_ticket_metadata_carries_execution_lifecycle_snapshot(tmp_path):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    metadata = create_ticket_metadata(
        ticket="T-LIFE",
        hypothesis_id="hyp-life",
        thesis_key="thesis-life",
        strategy_family="micro_momentum",
        expected_mechanism="continuation",
        side="buy",
        entry_price=1.1,
        stop_loss=1.099,
        target_price=1.102,
        max_hold_s=5,
        regime="trend",
        session="london",
        symbol="EURUSD",
        selected_horizon_s=5,
        model_artifact={"version": "v1", "status": "SHADOW_ONLY"},
        prediction_snapshot={"probability": 0.8},
        feature_snapshot={"return_5s": 0.0001},
        p_captured_win=0.8,
        expected_net_pnl=0.04,
        expected_net_pnl_lcb95=0.01,
        expected_mfe=0.06,
        expected_mae=-0.02,
        expected_time_to_green_s=2.0,
        tail_loss_probability=0.1,
        spread_assumption=0.0001,
        slippage_assumption=0.00002,
        commission_assumption=0.01,
        decision_reasons=["captured_exit_replay_positive"],
        sell_rejection_reason="lower_captured_probability",
        abstain_reason="none",
    )

    assert store.add(metadata)
    restored = TicketMetadataStore(tmp_path / "tickets.json").get("T-LIFE")
    assert restored is not None
    assert restored.selected_horizon_s == 5
    assert restored.p_captured_win == pytest.approx(0.8)
    assert restored.model_artifact == {"version": "v1", "status": "SHADOW_ONLY"}
    assert restored.decision_reasons == ["captured_exit_replay_positive"]


def test_order_margin_for_send_uses_broker_native_calculator_for_cross_currency_pair():
    class _Engine:
        def order_margin(self, symbol, side, quantity, price):
            assert (symbol, side, quantity, price) == ("USDJPY", "buy", 0.03, 159.38)
            return 30.0

    margin, source = order_margin_for_send(
        _Engine(), symbol="USDJPY", side="buy", quantity=0.03, price=159.38,
        contract_size=100000.0, leverage=100.0,
    )

    assert margin == 30.0
    assert source == "broker_native"


def test_intelligent_refresh_uses_candidate_spread_allowance_not_legacy_ceiling():
    allowance = candidate_spread_limit(
        entry=1.1000, target=1.1010, slippage_price=0.0001,
        commission_round_trip_usd=0.0, usd_per_price_unit=1000.0,
    )

    verdict = refresh_verdict(
        new_age_s=0.1, new_spread=0.00005, max_age_s=5.0,
        max_spread=0.00003, candidate_spread_limit=allowance,
    )

    assert allowance == pytest.approx(0.0009)
    assert verdict.ok is True


def test_runner_derives_candidate_spread_limit_from_selected_economics():
    decision = type("Decision", (), {
        "journal": {
            "exploration_economics": {
                "econ_entry": 1.1000,
                "econ_target": 1.1010,
                "econ_usd_per_price_unit": 1000.0,
            }
        }
    })()

    assert intelligent_refresh_spread_limit(
        decision, {"commission_round_trip_usd": 0.0, "slippage_bps": 0.0}
    ) == pytest.approx(0.001)


def test_intelligent_refresh_rejects_destructive_candidate_spread():
    verdict = refresh_verdict(
        new_age_s=0.1, new_spread=0.0002, max_age_s=5.0,
        max_spread=0.00003, candidate_spread_limit=0.0001,
    )

    assert verdict.ok is False
    assert verdict.reason == "spread_widened_beyond_candidate_limit"


def test_legacy_refresh_still_uses_universal_spread_ceiling():
    verdict = refresh_verdict(
        new_age_s=0.1, new_spread=0.00005, max_age_s=5.0,
        max_spread=0.00003,
    )

    assert verdict.ok is False
    assert verdict.reason == "spread_widened_beyond_max"


def test_exploration_order_risk_check_rejects_stale_quote_size_breach():
    """A refreshed quote must not let the sent lot size exceed $0.15 risk."""
    result = exploration_order_risk_check(
        order_qty=0.03,
        entry=1.38593,
        stop=1.38586,
        pip=0.0001,
        max_risk_usd=0.15,
        spec={
            "trade_contract_size": 100000.0,
            "trade_tick_value": 0.7215423689679059,
            "trade_tick_size": 0.00001,
            "volume_min": 0.01,
            "volume_step": 0.01,
        },
    )

    assert result["allowed"] is False
    assert result["reason"] == "exploration_risk_exceeds_budget"
    assert result["max_lots"] == 0.02


def test_video_style_prediction_signal_uses_shared_direction_only_when_enabled():
    frame = pd.DataFrame({
        "time": pd.date_range("2026-01-01", periods=3, freq="min", tz="UTC"),
        "open": [1.09995, 1.10045, 1.10145],
        "high": [1.10012, 1.10062, 1.10162],
        "low": [1.09988, 1.10038, 1.10138],
        "close": [1.10000, 1.10050, 1.10150],
    })

    signal = video_style_signal_for_scan(frame, symbol="EURUSD", enabled=True)

    assert signal is not None
    assert signal.side == "buy"
    assert video_style_signal_for_scan(frame, symbol="EURUSD", enabled=False) is None


def test_firehose_decision_snapshot_records_why_side_and_prediction_evidence():
    class Decision:
        side = "sell"
        reason = "short_horizon_eligible"
        expected_net_value = 0.04
        journal = {
            "exploration": True,
            "hypothesis_id": "hyp-123",
            "setup_family": "video_style_breakout",
            "regime": "trend",
            "structure": "breakout",
            "session": "new_york",
            "short_horizon_prediction": {
                "probability": 0.81,
                "expected_net_pnl": 0.04,
                "expected_mfe": 0.06,
                "expected_mae": -0.02,
                "expected_time_to_green_s": 3,
                "tail_loss_probability": 0.01,
                "feature_snapshot": {"return_3s": -0.0002},
                "side_comparison": {
                    "selected_side": "sell",
                    "ranking": ["sell", "buy"],
                },
            },
            "econ_ok": True,
            "econ_expected_net_usd": 0.04,
            "econ_p_win": 0.81,
        }

    snapshot = firehose_decision_snapshot(
        decision=Decision(), symbol="EURUSD", scan_id="scan-1", bar_time="t-1",
        side="sell", qty=0.01, entry=1.1, stop=1.101, target=1.097,
        spread=0.0001, quote_age=0.1,
    )

    assert snapshot["why"] == "WHY_SELL"
    assert snapshot["lane"] == "exploration"
    assert snapshot["hypothesis_id"] == "hyp-123"
    assert snapshot["prediction"]["side_comparison"]["selected_side"] == "sell"
    assert snapshot["economics"]["expected_net_usd"] == 0.04
    assert snapshot["risk"]["quantity"] == 0.01


def test_normalize_protective_stops_buy_respects_broker_min_distance():
    sl, tp = normalize_protective_stops(
        side="buy",
        entry=1.10020,
        sl=1.10015,
        tp=1.10025,
        spec={"point": 0.00001, "trade_stops_level": 20, "trade_freeze_level": 0},
        fallback_step=0.0001,
    )
    assert sl == 1.10000
    assert tp == 1.10040


def test_normalize_protective_stops_sell_respects_broker_min_distance():
    sl, tp = normalize_protective_stops(
        side="sell",
        entry=159.500,
        sl=159.505,
        tp=159.495,
        spec={"point": 0.001, "trade_stops_level": 10, "trade_freeze_level": 0},
        fallback_step=0.01,
    )
    assert sl == 159.510
    assert tp == 159.490


def test_close_ticket_confirmed_rejects_ok_response_when_ticket_remains_open():
    """A pending or partial close must not release Firehose lifecycle state."""
    positions = [
        PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.1, ticket="T1",
        )
    ]

    assert close_ticket_confirmed(positions, "T1") is False


def test_close_ticket_confirmed_accepts_absent_exact_ticket():
    positions = [
        PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.1, ticket="T2",
        )
    ]

    assert close_ticket_confirmed(positions, "T1") is True


def test_broker_close_evidence_is_authoritative_and_fail_closed():
    facts = broker_close_evidence(
        [
            {
                "ticket": "D1", "order": "O1", "position_id": "T1",
                "symbol": "EURUSD", "entry": 1, "profit": 0.20,
                "commission": -0.02, "swap": -0.01, "fee": -0.01,
                "qty": 0.01, "price": 1.101, "time": "2026-08-25T10:00:01Z",
            }
        ],
        ticket="T1",
    )

    assert facts["status"] == "BROKER_CONFIRMED"
    assert facts["realized_net_usd"] == pytest.approx(0.16)
    assert facts["cost_usd"] == pytest.approx(0.04)
    assert broker_close_evidence([], ticket="T1") == {
        "status": "INCOMPLETE_BROKER_EVIDENCE",
        "reason": "exact_exit_deal_not_available",
    }


def _contract(symbol: str) -> dict[str, float | str]:
    return {
        "name": symbol,
        "trade_tick_size": 0.00001,
        "trade_tick_value": 1.0,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
    }


def _basket_metadata(symbol: str = "EURUSD") -> dict[str, object]:
    return {
        "basket_id": "basket-1001",
        "hypothesis_id": "hyp-1",
        "family": "breakout",
        "symbol": symbol,
        "side": "buy",
        "trigger_id": "trigger-1",
        "entry_price": 1.1000,
        "stop_loss": 1.09985,
        "risk_budget": 0.15,
        "clip_cap": 1,
        "regime": "trend",
        "session": "london",
        "cost_evidence": {"spread_usd": 0.01, "commission_usd": 0.02},
    }


def _ticket_metadata(basket_id: str | None = "basket-1001"):
    return create_ticket_metadata(
        ticket="T1",
        hypothesis_id="hyp-1",
        thesis_key="thesis-1",
        strategy_family="breakout",
        expected_mechanism="continuation",
        side="buy",
        entry_price=1.1,
        stop_loss=1.09985,
        target_price=None,
        max_hold_s=300,
        regime="trend",
        session="london",
        symbol="EURUSD",
        basket_id=basket_id,
        trigger_id="trigger-1",
        clip_sequence=1,
        entry_geometry={"entry_price": 1.1, "stop_loss": 1.09985},
        initial_risk=0.15,
        cost_evidence={"spread_usd": 0.01, "commission_usd": 0.02},
    )


def _persisted_cleanup_state(
    tmp_path, *, basket_id: str | None = "basket-1001", persist_basket: bool = True,
):
    if persist_basket:
        persist_confirmed_firehose_basket(
            root=tmp_path, ticket_id="T1", metadata=_basket_metadata(),
            contract=_contract("EURUSD"), volume=0.01,
        )
    metadata_path = tmp_path / "ticket_metadata.json"
    metadata_store = TicketMetadataStore(metadata_path)
    metadata_store.add(_ticket_metadata(basket_id))
    return metadata_path, metadata_store


def test_confirmed_fill_persists_exact_one_clip_basket_in_symbol_store(tmp_path):
    result = persist_confirmed_firehose_basket(
        root=tmp_path,
        ticket_id="T1",
        metadata=_basket_metadata(),
        contract=_contract("EURUSD"),
        volume=0.01,
    )

    assert result == {
        "status": "PERSISTED",
        "basket_id": "basket-1001",
        "ticket_id": "T1",
        "initial_risk_usd": 0.15,
        "entry_price": 1.1,
        "stop_loss": 1.09985,
    }
    assert (tmp_path / "intel" / "firehose_baskets" / "EURUSD.json").is_file()


def test_confirmed_firehose_open_persists_decision_snapshot(tmp_path):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    metrics = TurnoverMetrics()
    journal = tmp_path / "journal.jsonl"
    position = PositionSnapshot(
        symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.10000,
        stop_loss=1.09985, ticket="T1",
    )

    result = record_confirmed_firehose_open(
        root=tmp_path, metadata_store=store, metrics=metrics, journal=journal,
        ticket_id="T1", position=position, basket_metadata=_basket_metadata(),
        ticket_metadata=_ticket_metadata(), opened_at=10.0, slot_capacity=1,
        contract=_contract("EURUSD"), decision_snapshot={"why": "WHY_BUY"},
    )

    assert result["status"] == "PERSISTED"
    assert store.get("T1").decision_snapshot == {"why": "WHY_BUY"}
    assert '"decision_snapshot": {"why": "WHY_BUY"}' in journal.read_text(encoding="utf-8")


def test_unconfirmed_fill_does_not_create_basket_store(tmp_path):
    result = persist_confirmed_firehose_basket(
        root=tmp_path,
        ticket_id=None,
        metadata=_basket_metadata(),
        contract=_contract("EURUSD"),
        volume=0.01,
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "unconfirmed_fill"}
    assert not (tmp_path / "intel" / "firehose_baskets").exists()


def test_invalid_symbol_contract_does_not_persist_basket(tmp_path):
    result = persist_confirmed_firehose_basket(
        root=tmp_path,
        ticket_id="T1",
        metadata=_basket_metadata(),
        contract=_contract("GBPUSD"),
        volume=0.01,
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    assert not (tmp_path / "intel" / "firehose_baskets").exists()


def test_confirmed_position_geometry_uses_broker_average_and_stop():
    geometry = confirmed_position_geometry(
        PositionSnapshot(
            symbol="EURUSD", side="buy", quantity=0.01,
            avg_price=1.10012, stop_loss=1.09985, ticket="T1",
        ),
    )

    assert geometry == {"entry_price": 1.10012, "stop_loss": 1.09985, "volume": 0.01}


def test_confirmed_position_geometry_rejects_missing_broker_stop():
    geometry = confirmed_position_geometry(
        PositionSnapshot(symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.10012, ticket="T1"),
    )

    assert geometry == {"status": "NO_EVIDENCE", "reason": "missing_confirmed_geometry"}


def test_missing_confirmed_geometry_creates_no_firehose_open_lifecycle(tmp_path):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    metrics = TurnoverMetrics()
    journal = tmp_path / "journal.jsonl"

    result = record_confirmed_firehose_open(
        root=tmp_path, metadata_store=store, metrics=metrics, journal=journal,
        ticket_id="T1", position=None, basket_metadata=_basket_metadata(),
        ticket_metadata=_ticket_metadata(), opened_at=10.0, slot_capacity=1,
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_confirmed_geometry"}
    assert store.get("T1") is None
    assert metrics.active_tickets == set()
    assert not journal.exists()
    assert not (tmp_path / "intel" / "firehose_baskets").exists()


def test_metadata_save_failure_rolls_back_firehose_open_lifecycle(tmp_path, monkeypatch):
    store = TicketMetadataStore(tmp_path / "tickets.json")
    metrics = TurnoverMetrics()
    journal = tmp_path / "journal.jsonl"
    monkeypatch.setattr(TicketMetadataStore, "_save", lambda self: False)
    position = PositionSnapshot(
        symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.10012,
        stop_loss=1.09985, ticket="T1",
    )

    result = record_confirmed_firehose_open(
        root=tmp_path, metadata_store=store, metrics=metrics, journal=journal,
        ticket_id="T1", position=position, basket_metadata=_basket_metadata(),
        ticket_metadata=_ticket_metadata(), opened_at=10.0, slot_capacity=1,
        contract=_contract("EURUSD"),
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "pending_basket_cleanup_persistence_failed"}
    assert store.get("T1") is None
    assert metrics.active_tickets == set()
    assert not journal.exists()
    basket_store = BasketMetadataStore(
        tmp_path / "intel" / "firehose_baskets" / "EURUSD.json",
        trusted_contract=ContractSpec.from_mapping("EURUSD", _contract("EURUSD")),
    )
    assert basket_store.get_ticket("T1") is None


def test_basket_persistence_failure_creates_no_firehose_open_lifecycle(tmp_path, monkeypatch):
    metadata_path = tmp_path / "tickets.json"
    store = TicketMetadataStore(metadata_path)
    metrics = TurnoverMetrics()
    journal = tmp_path / "journal.jsonl"
    position = PositionSnapshot(
        symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.10012,
        stop_loss=1.09985, ticket="T1",
    )

    monkeypatch.setattr(BasketMetadataStore, "_save", lambda self: (_ for _ in ()).throw(OSError("disk")))
    result = record_confirmed_firehose_open(
        root=tmp_path, metadata_store=store, metrics=metrics, journal=journal,
        ticket_id="T1", position=position, basket_metadata=_basket_metadata(),
        ticket_metadata=_ticket_metadata(), opened_at=10.0, slot_capacity=1,
        contract=_contract("EURUSD"),
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") == {
        "ticket_id": "T1", "basket_id": "basket-1001", "symbol": "EURUSD",
    }
    assert store.get("T1") is None
    assert metrics.active_tickets == set()
    assert not journal.exists()


def test_metadata_add_and_basket_compensation_save_failures_leave_restart_safe_cleanup(tmp_path, monkeypatch):
    """A failed opening cannot leave an unusable basket after restart."""
    metadata_path = tmp_path / "tickets.json"
    basket_path = tmp_path / "intel" / "firehose_baskets" / "EURUSD.json"
    store = TicketMetadataStore(metadata_path)
    metrics = TurnoverMetrics()
    journal = tmp_path / "journal.jsonl"
    position = PositionSnapshot(
        symbol="EURUSD", side="buy", quantity=0.01, avg_price=1.1000,
        stop_loss=1.09985, ticket="T1",
    )
    original_metadata_save = TicketMetadataStore._save
    original_basket_save = BasketMetadataStore._save
    metadata_save_calls = 0
    basket_save_calls = 0

    def fail_metadata_add_once(self):
        nonlocal metadata_save_calls
        metadata_save_calls += 1
        return metadata_save_calls != 2 and original_metadata_save(self)

    def fail_basket_compensation_save(self):
        nonlocal basket_save_calls
        basket_save_calls += 1
        if basket_save_calls == 3:
            raise OSError("simulated basket compensation persistence failure")
        return original_basket_save(self)

    monkeypatch.setattr(TicketMetadataStore, "_save", fail_metadata_add_once)
    monkeypatch.setattr(BasketMetadataStore, "_save", fail_basket_compensation_save)
    result = record_confirmed_firehose_open(
        root=tmp_path, metadata_store=store, metrics=metrics, journal=journal,
        ticket_id="T1", position=position, basket_metadata=_basket_metadata(),
        ticket_metadata=_ticket_metadata(), opened_at=10.0, slot_capacity=1,
        contract=_contract("EURUSD"),
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "ticket_metadata_persistence_failed"}
    assert store.get("T1") is None
    assert metrics.active_tickets == set()
    assert not journal.exists()
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") == {
        "ticket_id": "T1", "basket_id": "basket-1001", "symbol": "EURUSD",
    }
    trusted_contract = ContractSpec.from_mapping("EURUSD", _contract("EURUSD"))
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_ticket("T1") is not None

    monkeypatch.setattr(TicketMetadataStore, "_save", original_metadata_save)
    restored_store = TicketMetadataStore(metadata_path)
    assert reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=restored_store,
        guard=FirehoseReentryGuard(),
        positions=[position],
        contract_for_symbol=_contract,
        closed_at=20.0,
    ) == []
    assert restored_store.pending_basket_cleanup("T1") is not None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_ticket("T1") is not None

    failed_retry = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=restored_store,
        guard=FirehoseReentryGuard(),
        positions=[],
        contract_for_symbol=_contract,
        closed_at=20.0,
    )

    assert failed_retry == [{
        "ticket_id": "T1", "status": "NO_EVIDENCE", "reason": "invalid_broker_contract",
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is not None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_ticket("T1") is not None

    monkeypatch.setattr(BasketMetadataStore, "_save", original_basket_save)
    retried = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=TicketMetadataStore(metadata_path),
        guard=FirehoseReentryGuard(),
        positions=[],
        contract_for_symbol=_contract,
        closed_at=30.0,
    )

    assert retried == [{
        "ticket_id": "T1",
        "status": "REMOVED",
        "basket_removal": {
            "status": "REMOVED", "basket_id": "basket-1001", "basket_closed": True,
        },
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_basket("basket-1001") is None


def test_pending_basket_cleanup_keeps_zero_quantity_exact_ticket(tmp_path):
    metadata_path = tmp_path / "tickets.json"
    store = TicketMetadataStore(metadata_path)
    assert store.begin_pending_basket_cleanup("T1", "basket-1001", "EURUSD")
    persist_confirmed_firehose_basket(
        root=tmp_path, ticket_id="T1", metadata=_basket_metadata(),
        contract=_contract("EURUSD"), volume=0.01,
    )
    zero_quantity_position = PositionSnapshot(
        symbol="EURUSD", side="buy", quantity=0.0, avg_price=1.1, ticket="T1",
    )

    assert reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path, metadata_store=store, guard=FirehoseReentryGuard(),
        positions=[zero_quantity_position], contract_for_symbol=_contract, closed_at=20.0,
    ) == []
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is not None
    assert BasketMetadataStore(
        tmp_path / "intel" / "firehose_baskets" / "EURUSD.json",
        trusted_contract=ContractSpec.from_mapping("EURUSD", _contract("EURUSD")),
    ).get_ticket("T1") is not None


def test_pending_basket_cleanup_recovers_interruption_before_basket_persistence(tmp_path):
    metadata_path = tmp_path / "tickets.json"
    store = TicketMetadataStore(metadata_path)
    assert store.begin_pending_basket_cleanup("T1", "basket-1001", "EURUSD")

    assert reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path, metadata_store=store, guard=FirehoseReentryGuard(),
        positions=[], contract_for_symbol=_contract, closed_at=20.0,
    ) == [{
        "ticket_id": "T1",
        "status": "REMOVED",
        "basket_removal": {
            "status": "REMOVED", "basket_id": "basket-1001", "basket_closed": False,
        },
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is None


def test_pending_basket_cleanup_recovers_after_marker_clear_persistence_failure(tmp_path, monkeypatch):
    metadata_path = tmp_path / "tickets.json"
    store = TicketMetadataStore(metadata_path)
    assert store.begin_pending_basket_cleanup("T1", "basket-1001", "EURUSD")
    persist_confirmed_firehose_basket(
        root=tmp_path, ticket_id="T1", metadata=_basket_metadata(),
        contract=_contract("EURUSD"), volume=0.01,
    )
    original_save = TicketMetadataStore._save
    monkeypatch.setattr(TicketMetadataStore, "_save", lambda self: False)

    failed = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path, metadata_store=store, guard=FirehoseReentryGuard(),
        positions=[], contract_for_symbol=_contract, closed_at=20.0,
    )

    assert failed == [{
        "ticket_id": "T1",
        "status": "NO_EVIDENCE",
        "reason": "pending_basket_cleanup_persistence_failed",
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is not None
    assert BasketMetadataStore(
        tmp_path / "intel" / "firehose_baskets" / "EURUSD.json",
        trusted_contract=ContractSpec.from_mapping("EURUSD", _contract("EURUSD")),
    ).get_ticket("T1") is None

    monkeypatch.setattr(TicketMetadataStore, "_save", original_save)
    recovered = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path, metadata_store=TicketMetadataStore(metadata_path), guard=FirehoseReentryGuard(),
        positions=[], contract_for_symbol=_contract, closed_at=30.0,
    )

    assert recovered == [{
        "ticket_id": "T1",
        "status": "REMOVED",
        "basket_removal": {
            "status": "REMOVED", "basket_id": "basket-1001", "basket_closed": False,
        },
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is None


def test_pending_basket_marker_restart_runs_exact_close_cleanup_when_clear_fails(tmp_path, monkeypatch):
    """A failed marker clear cannot strand exact ticket metadata after restart."""
    metadata_path, store = _persisted_cleanup_state(tmp_path)
    basket_path = tmp_path / "intel" / "firehose_baskets" / "EURUSD.json"
    trusted_contract = ContractSpec.from_mapping("EURUSD", _contract("EURUSD"))
    assert store.begin_pending_basket_cleanup("T1", "basket-1001", "EURUSD")
    original_clear = TicketMetadataStore.clear_pending_basket_cleanup
    monkeypatch.setattr(TicketMetadataStore, "clear_pending_basket_cleanup", lambda self, ticket: False)

    failed = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path, metadata_store=store, guard=FirehoseReentryGuard(),
        positions=[], contract_for_symbol=_contract, closed_at=20.0,
    )

    assert failed == [{
        "ticket_id": "T1",
        "status": "NO_EVIDENCE",
        "reason": "pending_basket_cleanup_persistence_failed",
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is not None
    assert TicketMetadataStore(metadata_path).pending_cleanup("T1") is None
    assert TicketMetadataStore(metadata_path).get("T1") is None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_basket("basket-1001") is None

    monkeypatch.setattr(TicketMetadataStore, "clear_pending_basket_cleanup", original_clear)
    recovered = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path, metadata_store=TicketMetadataStore(metadata_path), guard=FirehoseReentryGuard(),
        positions=[], contract_for_symbol=_contract, closed_at=30.0,
    )

    assert recovered == [{
        "ticket_id": "T1",
        "status": "REMOVED",
        "basket_removal": {
            "status": "REMOVED", "basket_id": "basket-1001", "basket_closed": False,
        },
    }]
    assert TicketMetadataStore(metadata_path).pending_basket_cleanup("T1") is None
    assert TicketMetadataStore(metadata_path).pending_cleanup("T1") is None
    assert TicketMetadataStore(metadata_path).get("T1") is None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_basket("basket-1001") is None


def test_confirmed_close_removes_persisted_symbol_basket(tmp_path):
    persist_confirmed_firehose_basket(
        root=tmp_path, ticket_id="T1", metadata=_basket_metadata(), contract=_contract("EURUSD"), volume=0.01,
    )

    result = remove_confirmed_firehose_basket(
        root=tmp_path, ticket_id="T1", symbol="EURUSD", contract=_contract("EURUSD"),
    )

    assert result == {"status": "REMOVED", "basket_id": "basket-1001", "basket_closed": True}


def test_primary_lifecycle_identity_comes_only_from_ticket_metadata():
    meta = _ticket_metadata()

    assert firehose_lifecycle_identity(meta) == {
        "basket_id": "basket-1001", "trigger_id": "trigger-1", "clip_sequence": 1,
    }


def test_primary_lifecycle_identity_omits_incomplete_ticket_metadata():
    meta = _ticket_metadata()
    meta.clip_sequence = True

    assert firehose_lifecycle_identity(meta) == {}


def test_invalid_creation_inputs_remain_non_identifying_ticket_metadata():
    for basket_id, trigger_id, clip_sequence in (
        (True, "trigger-1", 1),
        ("basket-1001", 1, 1),
        ("basket-1001", "trigger-1", True),
        ("basket-1001", "trigger-1", 1.0),
    ):
        meta = create_ticket_metadata(
            ticket="T1",
            hypothesis_id="hyp-1",
            thesis_key="thesis-1",
            strategy_family="breakout",
            expected_mechanism="continuation",
            side="buy",
            entry_price=1.1,
            stop_loss=1.09985,
            target_price=None,
            max_hold_s=300,
            regime="trend",
            session="london",
            symbol="EURUSD",
            basket_id=basket_id,
            trigger_id=trigger_id,
            clip_sequence=clip_sequence,
        )

        assert firehose_lifecycle_identity(meta) == {}


def test_confirmed_basket_cleanup_retries_after_basket_save_failure(tmp_path, monkeypatch):
    metadata_path, metadata_store = _persisted_cleanup_state(tmp_path)
    guard_path = tmp_path / "firehose_reentry_guard.json"
    guard = FirehoseReentryGuard(guard_path)
    basket_path = tmp_path / "intel" / "firehose_baskets" / "EURUSD.json"
    trusted_contract = ContractSpec.from_mapping("EURUSD", _contract("EURUSD"))
    original_save = BasketMetadataStore._save

    def fail_save(self):
        raise OSError("simulated basket persistence failure")

    monkeypatch.setattr(BasketMetadataStore, "_save", fail_save)
    failed = remove_confirmed_firehose_basket_then_cleanup(
        root=tmp_path,
        metadata_store=metadata_store,
        guard=guard,
        ticket_id="T1",
        quote_fingerprint="quote-1",
        closed_at=10.0,
        contract=_contract("EURUSD"),
    )

    assert failed == {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    assert metadata_store.get("T1") is not None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_basket("basket-1001") is not None
    assert guard.allows("thesis-1", "quote-1", 11.0) == (True, "fresh_quote")

    monkeypatch.setattr(BasketMetadataStore, "_save", original_save)
    retried = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=TicketMetadataStore(metadata_path),
        guard=FirehoseReentryGuard(guard_path),
        positions=[],
        contract_for_symbol=_contract,
        closed_at=10.0,
    )

    assert retried == [{
        "status": "CLEANED",
        "ticket_id": "T1",
        "basket_removal": {
        "status": "REMOVED", "basket_id": "basket-1001", "basket_closed": True,
        },
    }]
    assert TicketMetadataStore(metadata_path).get("T1") is None
    assert BasketMetadataStore(basket_path, trusted_contract=trusted_contract).get_basket("basket-1001") is None
    assert FirehoseReentryGuard(guard_path).allows("thesis-1", "quote-1", 11.0) == (False, "stale_reentry")


def test_confirmed_basket_cleanup_retains_state_for_invalid_contract(tmp_path):
    _, metadata_store = _persisted_cleanup_state(tmp_path)
    guard = FirehoseReentryGuard()

    result = remove_confirmed_firehose_basket_then_cleanup(
        root=tmp_path, metadata_store=metadata_store, guard=guard, ticket_id="T1",
        quote_fingerprint="quote-1", closed_at=10.0, contract=_contract("GBPUSD"),
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "invalid_broker_contract"}
    assert metadata_store.get("T1") is not None
    assert guard.allows("thesis-1", "quote-1", 11.0) == (True, "fresh_quote")


def test_confirmed_basket_cleanup_retains_state_for_missing_persisted_ticket(tmp_path):
    _, metadata_store = _persisted_cleanup_state(
        tmp_path, basket_id="basket-1001", persist_basket=False,
    )
    guard = FirehoseReentryGuard()

    result = remove_confirmed_firehose_basket_then_cleanup(
        root=tmp_path, metadata_store=metadata_store, guard=guard, ticket_id="T1",
        quote_fingerprint="quote-1", closed_at=10.0, contract=_contract("EURUSD"),
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}
    assert metadata_store.get("T1") is not None
    assert guard.allows("thesis-1", "quote-1", 11.0) == (True, "fresh_quote")


def test_confirmed_basket_cleanup_rejects_mismatched_basket_ownership(tmp_path):
    _, metadata_store = _persisted_cleanup_state(tmp_path, basket_id="other-basket")
    persist_confirmed_firehose_basket(
        root=tmp_path, ticket_id="T1", metadata=_basket_metadata(),
        contract=_contract("EURUSD"), volume=0.01,
    )
    guard = FirehoseReentryGuard()

    result = remove_confirmed_firehose_basket_then_cleanup(
        root=tmp_path, metadata_store=metadata_store, guard=guard, ticket_id="T1",
        quote_fingerprint="quote-1", closed_at=10.0, contract=_contract("EURUSD"),
    )

    assert result == {"status": "NO_EVIDENCE", "reason": "missing_persisted_ticket"}
    assert metadata_store.get("T1") is not None
    assert BasketMetadataStore(
        tmp_path / "intel" / "firehose_baskets" / "EURUSD.json",
        trusted_contract=ContractSpec.from_mapping("EURUSD", _contract("EURUSD")),
    ).get_basket("basket-1001") is not None
    assert guard.allows("thesis-1", "quote-1", 11.0) == (True, "fresh_quote")


def test_reconciliation_recovers_after_basket_removal_marker_save_failure(tmp_path, monkeypatch):
    metadata_path, metadata_store = _persisted_cleanup_state(tmp_path)
    guard_path = tmp_path / "firehose_reentry_guard.json"
    guard = FirehoseReentryGuard(guard_path)
    original_save = TicketMetadataStore._save
    save_calls = 0

    def fail_second_save(self):
        nonlocal save_calls
        save_calls += 1
        return save_calls != 2 and original_save(self)

    monkeypatch.setattr(TicketMetadataStore, "_save", fail_second_save)
    failed = remove_confirmed_firehose_basket_then_cleanup(
        root=tmp_path, metadata_store=metadata_store, guard=guard, ticket_id="T1",
        quote_fingerprint="quote-1", closed_at=10.0, contract=_contract("EURUSD"),
    )

    assert failed == {"status": "NO_EVIDENCE", "reason": "ticket_metadata_persistence_failed"}
    assert TicketMetadataStore(metadata_path).get("T1") is not None
    assert TicketMetadataStore(metadata_path).pending_cleanup("T1")["basket_removed"] is False

    monkeypatch.setattr(TicketMetadataStore, "_save", original_save)
    retried = reconcile_confirmed_firehose_basket_cleanups(
        root=tmp_path,
        metadata_store=TicketMetadataStore(metadata_path),
        guard=FirehoseReentryGuard(guard_path),
        positions=[],
        contract_for_symbol=_contract,
        closed_at=20.0,
    )

    assert retried[0]["status"] == "CLEANED"
    assert TicketMetadataStore(metadata_path).get("T1") is None
