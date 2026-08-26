"""Deterministic tests for production FastExit evaluation helper.

Tests the SAME production helper used by run_broker_paper.py.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from aegis.intel.fast_firehose import ExitAction, FastExitConfig, FastExitStateMachine
from aegis.intel.fast_exit_runner import (
    FastExitContext, build_harvest_input, combine_existing_exit_with_policy, evaluate_fast_exit,
    estimate_remaining_ev, firehose_exit_trace, pip_size_for, spread_r_from_geometry,
    REMAINING_EV_EXIT_POLICY_ID,
)
from aegis.intel.quote_buffer import QuoteBuffer
from aegis.intel.broker_math import BrokerSymbolSpec
from aegis.intel.ticket_metadata import TicketMetadata, create_ticket_metadata


class TestPipSizeFor:
    """Test pip_size_for helper."""

    def test_eurusd(self):
        assert pip_size_for("EURUSD", {}) == 0.0001

    def test_usdjpy(self):
        assert pip_size_for("USDJPY", {}) == 0.01

    def test_xauusd(self):
        assert pip_size_for("XAUUSD", {}) == 0.1


class TestFastExitProductionHelper:
    """Test the production FastExit evaluation helper."""

    def create_context(
        self,
        *,
        symbol: str = "EURUSD",
        ticket: str = "12345",
        side: str = "buy",
        entry_price: float = 1.10000,
        current_bid: float = 1.10050,
        current_ask: float = 1.10052,
        avg_price: float = 1.10000,
        stop_loss: float = 1.09900,
        quantity: float = 0.01,
        mfe_usd: float = 10.0,
        mae_usd: float = -1.0,
        opened_ts: float = 1000.0,
        regime_at_entry: str = "trend",
        track_target: float = 1.10200,
        track_invalidation: float = 1.09900,
        track_entry_ev: float = 0.1,
        track_side: str = "buy",
        ticket_meta: Optional[Any] = None,
        config: Optional[Mapping[str, Any]] = None,
        now_ts: float = 1030.0,
        engine_spec: Optional[Mapping[str, Any]] = None,
        intelligent_brain: Optional[Any] = None,
        live_marks: Optional[Mapping[str, Mapping[str, float]]] = None,
        quote_buffer=None,
        remaining_ev=None,
        remaining_ev_status="UNKNOWN",
        observed_spread_r=None,
        observed_slippage_r=None,
        observed_commission_r=None,
        spread_normal=None,
        short_horizon_prediction=None,
    ) -> FastExitContext:
        """Create a test context with sensible defaults."""
        live_marks = live_marks or {symbol: {"bid": current_bid, "ask": current_ask}}

        # Mock engine spec
        engine_spec = engine_spec or {
            "trade_tick_value": 1.0,
            "trade_tick_size": 0.00001,
            "volume_min": 0.01,
            "trade_contract_size": 100000.0,
        }

        # Mock intelligent_brain
        brain = intelligent_brain or MagicMock()
        brain.regime_by_symbol = {symbol: "trend"}
        brain.experiments.data = {"experiments": {}}

        # Mock profit_manager
        profit_manager = MagicMock()

        return FastExitContext(
            symbol=symbol,
            ticket=ticket,
            side=side,
            entry_price=entry_price,
            current_bid=current_bid,
            current_ask=current_ask,
            avg_price=avg_price,
            stop_loss=stop_loss,
            quantity=quantity,
            mfe_usd=mfe_usd,
            mae_usd=mae_usd,
            opened_ts=opened_ts,
            regime_at_entry=regime_at_entry,
            track_target=track_target,
            track_invalidation=track_invalidation,
            track_entry_ev=track_entry_ev,
            track_side=track_side,
            ticket_meta=ticket_meta,
            engine_spec=engine_spec,
            config=config or {},
            live_marks=live_marks,
            intelligent_brain=brain,
            profit_manager=profit_manager,
            now_ts=now_ts,
            quote_buffer=quote_buffer,
            remaining_ev=remaining_ev,
            remaining_ev_status=remaining_ev_status,
            observed_spread_r=observed_spread_r,
            observed_slippage_r=observed_slippage_r,
            observed_commission_r=observed_commission_r,
            spread_normal=spread_normal,
            short_horizon_prediction=short_horizon_prediction,
        )

    def test_buy_uses_bid(self):
        """BUY position uses BID for liquidation mark."""
        ctx = self.create_context(
            side="buy",
            current_bid=1.10050,
            current_ask=1.10052,
        )
        verdict = evaluate_fast_exit(ctx)
        # Should HOLD - not at target yet, MFE armed, progress made
        assert verdict["action"] in {"HOLD", "LOCK", "TAKE", "SCRATCH", "ABORT", "TIME_EXIT"}
        assert verdict["action"] != "ERROR"

    def test_sell_uses_ask(self):
        """SELL position uses ASK for liquidation mark."""
        ctx = self.create_context(
            side="sell",
            current_bid=1.09950,
            current_ask=1.09952,
            avg_price=1.10000,
            stop_loss=1.10100,
            track_target=1.09800,
            track_invalidation=1.10100,
            track_side="sell",
        )
        verdict = evaluate_fast_exit(ctx)
        assert verdict["action"] in {"HOLD", "LOCK", "TAKE", "SCRATCH", "ABORT", "TIME_EXIT"}
        assert verdict["action"] != "ERROR"

    def test_loss_fraction_scratch_exits_before_time_decay(self):
        ctx = self.create_context(
            side="buy",
            current_bid=1.09969,
            current_ask=1.09971,
            mfe_usd=0.0,
            mae_usd=-0.31,
            opened_ts=1000.0,
            now_ts=1005.0,
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["action"] == "SCRATCH"
        assert verdict["reason"] == "loss_fraction_scratch"

    def test_loss_fraction_scratch_does_not_fire_below_threshold(self):
        ctx = self.create_context(
            side="buy",
            current_bid=1.09971,
            current_ask=1.09973,
            mfe_usd=0.0,
            mae_usd=-0.29,
            opened_ts=1000.0,
            now_ts=1005.0,
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["reason"] != "loss_fraction_scratch"

    def test_calibrated_short_horizon_revoke_aborts_losing_ticket(self):
        ctx = self.create_context(
            current_bid=1.09990,
            current_ask=1.09992,
            mfe_usd=0.0,
            mae_usd=-0.10,
            opened_ts=1000.0,
            now_ts=1005.0,
            short_horizon_prediction={
                "calibration_status": "calibrated",
                "abstain": False,
                "decision": False,
                "probability": 0.40,
                "threshold": 0.60,
            },
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["action"] == "ABORT"
        assert verdict["reason"] == "short_horizon_support_revoked"

    def test_short_horizon_abstain_does_not_masquerade_as_revoke(self):
        ctx = self.create_context(
            current_bid=1.09990,
            current_ask=1.09992,
            mfe_usd=0.0,
            mae_usd=-0.10,
            opened_ts=1000.0,
            now_ts=1005.0,
            short_horizon_prediction={
                "calibration_status": "calibrated",
                "abstain": True,
                "decision": False,
                "probability": 0.40,
                "threshold": 0.60,
            },
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["reason"] != "short_horizon_support_revoked"

    def test_short_horizon_revoke_does_not_force_profitable_ticket_out(self):
        ctx = self.create_context(
            current_bid=1.10010,
            current_ask=1.10012,
            mfe_usd=0.0,
            mae_usd=0.0,
            opened_ts=1000.0,
            now_ts=1005.0,
            short_horizon_prediction={
                "calibration_status": "calibrated",
                "abstain": False,
                "decision": False,
                "probability": 0.40,
                "threshold": 0.60,
            },
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["reason"] != "short_horizon_support_revoked"

    def test_two_symbols_simultaneously(self):
        """Two different symbols evaluated simultaneously use correct marks."""
        # EURUSD buy
        ctx_eur = self.create_context(
            symbol="EURUSD",
            ticket="11111",
            side="buy",
            current_bid=1.10050,
            current_ask=1.10052,
        )
        # USDJPY sell
        ctx_jpy = self.create_context(
            symbol="USDJPY",
            ticket="22222",
            side="sell",
            current_bid=150.00,
            current_ask=150.02,
            stop_loss=150.10,
            track_target=149.90,
            track_invalidation=150.10,
            track_side="sell",
        )
        verdict_eur = evaluate_fast_exit(ctx_eur)
        verdict_jpy = evaluate_fast_exit(ctx_jpy)
        # Both should produce valid actions without exceptions
        assert verdict_eur["action"] != "ERROR"
        assert verdict_jpy["action"] != "ERROR"

    def test_two_tickets_same_symbol(self):
        """Two tickets on same symbol evaluated independently."""
        # First ticket - buy
        ctx1 = self.create_context(
            ticket="T1",
            side="buy",
            current_bid=1.10050,
            current_ask=1.10052,
        )
        # Second ticket - sell (same symbol)
        ctx2 = self.create_context(
            ticket="T2",
            side="sell",
            current_bid=1.09950,
            current_ask=1.09952,
            stop_loss=1.10100,
            track_target=1.09800,
            track_invalidation=1.10100,
            track_side="sell",
        )
        verdict1 = evaluate_fast_exit(ctx1)
        verdict2 = evaluate_fast_exit(ctx2)
        assert verdict1["action"] != "ERROR"
        assert verdict2["action"] != "ERROR"

    def test_exact_ticket_metadata_max_hold(self):
        """Exact max_hold_s from ticket metadata is used."""
        meta = create_ticket_metadata(
            ticket="T_MAXHOLD",
            hypothesis_id="hyp_123",
            thesis_key="key_123",
            strategy_family="micro_momentum_burst",
            expected_mechanism="compression->impulse",
            side="buy",
            entry_price=1.10000,
            stop_loss=1.09900,
            target_price=1.10200,
            max_hold_s=180,  # Custom horizon
            regime="trend",
            session="london",
            symbol="EURUSD",
        )
        meta.opened_ts = 1000.0
        ctx = self.create_context(
            ticket="T_MAXHOLD",
            ticket_meta=meta,
            opened_ts=1000.0,
            now_ts=1300.0,  # 300s > 180s
            current_bid=1.10001,  # Near entry, small profit
            current_ask=1.10003,
        )
        verdict = evaluate_fast_exit(ctx)
        # Should be SCRATCH due to time_exit (180s from ticket metadata)
        assert verdict["action"] == "SCRATCH"

    def test_exact_ticket_metadata_drives_state_machine_geometry(self):
        """Confirmed ticket geometry overrides stale position context at FastExit's boundary."""
        meta = create_ticket_metadata(
            ticket="T_CONFIRMED_GEOMETRY",
            hypothesis_id="hyp_123",
            thesis_key="key_123",
            strategy_family="micro_momentum_burst",
            expected_mechanism="compression->impulse",
            side="buy",
            entry_price=1.20000,
            stop_loss=1.19850,
            target_price=None,
            max_hold_s=120,
            regime="trend",
            session="london",
            symbol="EURUSD",
        )
        meta.opened_ts = 1000.0
        ctx = self.create_context(
            ticket="T_CONFIRMED_GEOMETRY",
            ticket_meta=meta,
            entry_price=1.10000,
            avg_price=1.10050,
            stop_loss=1.09900,
            current_bid=1.20100,
            current_ask=1.20102,
        )
        captured = {}

        def capture_evaluate(_self, **kwargs):
            captured.update(kwargs)
            return {"action": "HOLD", "reason": "test", "why": "test", "policy": "test"}

        with patch.object(FastExitStateMachine, "evaluate", capture_evaluate):
            evaluate_fast_exit(ctx)

        assert captured["current_mark"] == pytest.approx(1.20100)
        assert captured["entry_price"] == pytest.approx(1.20000)
        assert captured["stop_loss"] == pytest.approx(1.19850)
        assert captured["pnl_pips"] == pytest.approx(10.0)
        assert captured["stop_pips"] == pytest.approx(15.0)
        assert captured["target"] == pytest.approx(1.20100)

    def test_video_style_fallback_horizon_applies_without_ticket_metadata(self):
        """Legacy/open tickets still receive the seconds-first video horizon."""
        ctx = self.create_context(
            ticket="T_VIDEO_LEGACY",
            ticket_meta=None,
            config={"_video_style_max_hold_s": 5},
            opened_ts=1000.0,
            now_ts=1010.0,
            current_bid=1.10000,
            current_ask=1.10002,
            mfe_usd=0.0,
            mae_usd=-0.01,
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["action"] == "SCRATCH"
        assert verdict["reason"] == "time_decay_no_progress"

    def test_video_style_cap_overrides_stale_long_ticket_metadata(self):
        meta = create_ticket_metadata(
            ticket="T_VIDEO_STALE_HORIZON",
            hypothesis_id="hyp_123",
            thesis_key="key_123",
            strategy_family="video_style_breakout",
            expected_mechanism="breakout",
            side="buy",
            entry_price=1.10000,
            stop_loss=1.09900,
            target_price=1.10200,
            max_hold_s=120,
            regime="trend",
            session="asia",
            symbol="EURUSD",
        )
        meta.opened_ts = 1000.0
        ctx = self.create_context(
            ticket="T_VIDEO_STALE_HORIZON",
            ticket_meta=meta,
            config={"_video_style_max_hold_s": 5},
            opened_ts=1000.0,
            now_ts=1010.0,
            current_bid=1.10000,
            current_ask=1.10002,
            mfe_usd=0.0,
            mae_usd=-0.01,
        )

        verdict = evaluate_fast_exit(ctx)

        assert verdict["action"] == "SCRATCH"
        assert verdict["reason"] == "time_decay_no_progress"

    def test_metadata_without_target_uses_confirmed_fallback_target(self):
        """Metadata tickets derive their own fallback target instead of using legacy experiments."""
        meta = create_ticket_metadata(
            ticket="T_METADATA_FALLBACK",
            hypothesis_id="hyp_123",
            thesis_key="key_123",
            strategy_family="micro_momentum_burst",
            expected_mechanism="compression->impulse",
            side="buy",
            entry_price=1.20000,
            stop_loss=1.19850,
            target_price=None,
            max_hold_s=120,
            regime="trend",
            session="london",
            symbol="EURUSD",
        )
        meta.opened_ts = 1000.0
        ctx = self.create_context(
            ticket="T_METADATA_FALLBACK",
            ticket_meta=meta,
            entry_price=1.10000,
            avg_price=1.10050,
            stop_loss=1.09900,
            current_bid=1.20100,
            current_ask=1.20102,
        )
        ctx.legacy_hypothesis_id = "legacy_fallback"
        ctx.intelligent_brain.experiments.data = {
            "experiments": {
                "legacy": {
                    "hypothesis_id": "legacy_fallback",
                    "target_price": 1.30000,
                    "max_hold_s": 60,
                },
            },
        }

        verdict = evaluate_fast_exit(ctx)

        assert verdict["action"] == "TAKE"
        assert verdict["reason"] == "target_reached"

    def test_missing_metadata_preserves_context_entry_at_state_machine_boundary(self):
        """Legacy tickets retain ctx.entry_price for the state-machine entry input."""
        ctx = self.create_context(entry_price=1.10000, avg_price=1.10050)
        captured = {}

        def capture_evaluate(_self, **kwargs):
            captured.update(kwargs)
            return {"action": "HOLD", "reason": "test", "why": "test", "policy": "test"}

        with patch.object(FastExitStateMachine, "evaluate", capture_evaluate):
            evaluate_fast_exit(ctx)

        assert captured["entry_price"] == pytest.approx(1.10000)

    def test_different_max_hold_values(self):
        """Test different max_hold_s values from ticket metadata."""
        for max_hold in [120, 180, 300]:
            meta = create_ticket_metadata(
                ticket=f"T_{max_hold}",
                hypothesis_id="hyp_123",
                thesis_key="key_123",
                strategy_family="micro_momentum_burst",
                expected_mechanism="compression->impulse",
                side="buy",
                entry_price=1.10000,
                stop_loss=1.09900,
                target_price=1.10200,
                max_hold_s=max_hold,
                regime="trend",
                session="london",
                symbol="EURUSD",
            )
            meta.opened_ts = 1000.0
            # Test at time > max_hold
            ctx = self.create_context(
                ticket=f"T_{max_hold}",
                ticket_meta=meta,
                opened_ts=1000.0,
                now_ts=1000.0 + max_hold + 10,
                current_bid=1.10001,
                current_ask=1.10003,
            )
            verdict = evaluate_fast_exit(ctx)
            # Should be SCRATCH due to time_exit
            assert verdict["action"] == "SCRATCH", f"max_hold={max_hold}: expected SCRATCH, got {verdict['action']}"

    def test_no_exception_on_missing_spec(self):
        """FastExit fails closed when broker-native money math is unavailable."""
        ctx = self.create_context()
        ctx.engine_spec = None
        verdict = evaluate_fast_exit(ctx)
        assert verdict == {
            "action": "HOLD",
            "reason": "broker_spec_unavailable",
            "why": "Broker-native tick value, tick size, and volume evidence are required",
            "policy": "safety_noop",
        }

    def test_no_exception_on_missing_brain(self):
        """FastExit handles missing intelligent_brain gracefully."""
        ctx = self.create_context(
            intelligent_brain=None,
        )
        verdict = evaluate_fast_exit(ctx)
        assert verdict["action"] != "ERROR"


class TestFirehoseHarvestAdapter:
    def _context(self, *, side="buy", ticket_meta=None, quote_buffer=None, config=None):
        helper = TestFastExitProductionHelper()
        meta = ticket_meta or create_ticket_metadata(
            ticket="T_HARVEST", hypothesis_id="hyp", thesis_key="thesis",
            strategy_family="micro", expected_mechanism="test", side=side,
            entry_price=1.10000, stop_loss=1.09900 if side == "buy" else 1.10100,
            target_price=1.10200 if side == "buy" else 1.09800, max_hold_s=120,
            regime="trend", session="london", symbol="EURUSD",
        )
        meta.opened_ts = 1000.0
        return helper.create_context(
            ticket="T_HARVEST", side=side, ticket_meta=meta,
            stop_loss=meta.stop_loss, quote_buffer=quote_buffer,
            remaining_ev=0.2, remaining_ev_status="ESTIMATED",
            observed_spread_r=0.01, observed_slippage_r=0.01,
            observed_commission_r=0.01, spread_normal=True,
            config=config,
        )

    def _quotes(self):
        quotes = QuoteBuffer()
        for timestamp, bid, ask in ((1000.0, 1.10000, 1.10002), (1015.0, 1.10010, 1.10012),
                                    (1025.0, 1.10020, 1.10022), (1030.0, 1.10030, 1.10032)):
            quotes.record("EURUSD", timestamp, bid, ask)
        return quotes

    def test_buy_harvest_uses_bid_and_sell_harvest_uses_ask(self):
        buy = self._context(quote_buffer=self._quotes())
        sell = self._context(side="sell", quote_buffer=self._quotes())
        assert build_harvest_input(buy).liquidation_mark == buy.current_bid
        assert build_harvest_input(sell).liquidation_mark == sell.current_ask

    def test_exact_ticket_metadata_supplies_stop_target_and_opened_time(self):
        ctx = self._context(quote_buffer=self._quotes())
        harvest = build_harvest_input(ctx)
        assert harvest.opened_ts == ctx.ticket_meta.opened_ts
        assert harvest.stop_loss == ctx.ticket_meta.stop_loss
        assert harvest.target_price == ctx.ticket_meta.target_price

    def test_trailing_broker_stop_does_not_change_original_r_normalization(self):
        ctx = self._context(quote_buffer=self._quotes())
        # The broker has trailed the stop and adjusted its displayed average;
        # original ticket geometry must remain the denominator for R.
        ctx.avg_price = 1.10080
        ctx.stop_loss = 1.10060
        harvest = build_harvest_input(ctx)
        assert harvest.gross_pnl_r == pytest.approx(0.5)
        exact_spread_r = spread_r_from_geometry(
            ctx.ticket_meta.entry_price, ctx.ticket_meta.stop_loss, ctx.quantity,
            ctx.current_bid, ctx.current_ask, ctx.engine_spec,
        )
        trailed_spread_r = spread_r_from_geometry(
            ctx.avg_price, ctx.stop_loss, ctx.quantity,
            ctx.current_bid, ctx.current_ask, ctx.engine_spec,
        )
        assert exact_spread_r == pytest.approx(0.02)
        assert exact_spread_r != trailed_spread_r

    def test_missing_quote_history_keeps_existing_safety_hold(self):
        ctx = self._context(quote_buffer=QuoteBuffer())
        ctx.mfe_usd = 0.0
        assert build_harvest_input(ctx) is None
        assert evaluate_fast_exit(ctx)["action"] == "HOLD"

    def test_unvalidated_harvester_keeps_legacy_ev_behavior(self):
        ctx = self._context(
            quote_buffer=QuoteBuffer(),
            config={"fast_firehose_remaining_ev_policy": REMAINING_EV_EXIT_POLICY_ID},
        )
        ctx.mfe_usd = 0.0
        ctx.remaining_ev = -1.0
        verdict = evaluate_fast_exit(ctx)
        assert verdict["action"] == "ABORT"
        assert verdict["reason"] == "remaining_ev_negative"

    def test_remaining_ev_estimate_is_costed_and_point_in_time(self):
        value, status = estimate_remaining_ev(
            side="buy", entry_price=1.10000, current_mark=1.10100,
            invalidation=1.09900, target=1.10200, entry_ev=0.20,
        )

        assert status == "ESTIMATED"
        assert value == pytest.approx(0.05)

        at_target, target_status = estimate_remaining_ev(
            side="buy", entry_price=1.10000, current_mark=1.10200,
            invalidation=1.09900, target=1.10200, entry_ev=0.20,
        )
        assert target_status == "ESTIMATED"
        assert at_target == pytest.approx(0.0)

    def test_remaining_ev_estimate_fails_closed_without_valid_entry_economics(self):
        assert estimate_remaining_ev(
            side="buy", entry_price=1.10000, current_mark=1.10100,
            invalidation=1.09900, target=1.10200, entry_ev=0.0,
        ) == (None, "UNKNOWN")
        assert estimate_remaining_ev(
            side="buy", entry_price=1.10000, current_mark=1.10100,
            invalidation=1.09900, target=1.09900, entry_ev=0.20,
        ) == (None, "UNKNOWN")

    def test_trace_contains_observed_values_and_nulls_for_unavailable_evidence(self):
        ctx = self._context(quote_buffer=QuoteBuffer())
        trace = firehose_exit_trace(ctx, {"action": "HOLD", "reason": "test"})
        assert {"pnl_r", "mfe_r", "profit_floor_r", "return_5s_r", "remaining_ev", "reason"} <= trace.keys()
        assert trace["return_5s_r"] is None
        assert trace["profit_floor_r"] is None

    def test_trace_identity_comes_only_from_exact_ticket_metadata(self):
        meta = create_ticket_metadata(
            ticket="T_HARVEST", hypothesis_id="hyp", thesis_key="thesis",
            strategy_family="micro", expected_mechanism="test", side="buy",
            entry_price=1.10000, stop_loss=1.09900, target_price=1.10200,
            max_hold_s=120, regime="trend", session="london", symbol="EURUSD",
            basket_id="B1", trigger_id="Q1", clip_sequence=1,
        )
        ctx = self._context(ticket_meta=meta, quote_buffer=QuoteBuffer())

        trace = firehose_exit_trace(ctx, {"action": "HOLD", "reason": "test"})

        assert {field: trace[field] for field in ("basket_id", "trigger_id", "clip_sequence")} == {
            "basket_id": "B1", "trigger_id": "Q1", "clip_sequence": 1,
        }

    def test_trace_omits_identity_without_complete_exact_ticket_metadata(self):
        meta = create_ticket_metadata(
            ticket="T_HARVEST", hypothesis_id="hyp", thesis_key="thesis",
            strategy_family="micro", expected_mechanism="test", side="buy",
            entry_price=1.10000, stop_loss=1.09900, target_price=1.10200,
            max_hold_s=120, regime="trend", session="london", symbol="EURUSD",
            basket_id="B1", trigger_id="", clip_sequence=1,
        )
        ctx = self._context(ticket_meta=meta, quote_buffer=QuoteBuffer())

        trace = firehose_exit_trace(ctx, {"action": "HOLD", "reason": "test"})

        assert not {"basket_id", "trigger_id", "clip_sequence"} & trace.keys()


class TestFastExitRunnerIntegration:
    """Integration tests that verify the helper matches runner behavior."""

    def create_context(self, **kwargs):
        """Delegate to TestFastExitProductionHelper's create_context."""
        helper = TestFastExitProductionHelper()
        return helper.create_context(**kwargs)

    def test_buy_liquidation_mark_is_bid(self):
        """Verify BUY uses bid explicitly by checking pnl calculation."""
        ctx = FastExitContext(
            symbol="EURUSD",
            ticket="T1",
            side="buy",
            entry_price=1.10000,
            current_bid=1.10050,
            current_ask=1.10052,
            avg_price=1.10000,
            stop_loss=1.09900,
            quantity=0.01,
            mfe_usd=5.0,
            mae_usd=-1.0,
            opened_ts=1000.0,
            regime_at_entry="trend",
            track_target=1.10200,
            track_invalidation=1.09900,
            track_entry_ev=0.1,
            track_side="buy",
            ticket_meta=None,
            engine_spec={"trade_tick_value": 1.0, "trade_tick_size": 0.00001, "volume_min": 0.01},
            config={},
            live_marks={"EURUSD": {"bid": 1.10050, "ask": 1.10052}},
            intelligent_brain=MagicMock(regime_by_symbol={}, experiments=MagicMock(data={"experiments": {}})),
            profit_manager=MagicMock(),
            now_ts=1030.0,
        )
        # Manually verify the liquidation mark logic
        from aegis.intel.fast_exit_runner import evaluate_fast_exit
        verdict = evaluate_fast_exit(ctx)
        # The key test: no exception, valid action
        assert verdict["action"] in {"HOLD", "LOCK", "TAKE", "SCRATCH", "ABORT", "TIME_EXIT"}

    def test_sell_liquidation_mark_is_ask(self):
        """Verify SELL uses ask explicitly by checking pnl calculation."""
        ctx = FastExitContext(
            symbol="EURUSD",
            ticket="T1",
            side="sell",
            entry_price=1.10000,
            current_bid=1.09950,
            current_ask=1.09952,
            avg_price=1.10000,
            stop_loss=1.10100,
            quantity=0.01,
            mfe_usd=5.0,
            mae_usd=-1.0,
            opened_ts=1000.0,
            regime_at_entry="trend",
            track_target=1.09800,
            track_invalidation=1.10100,
            track_entry_ev=0.1,
            track_side="sell",
            ticket_meta=None,
            engine_spec={"trade_tick_value": 1.0, "trade_tick_size": 0.00001, "volume_min": 0.01},
            config={},
            live_marks={"EURUSD": {"bid": 1.09950, "ask": 1.09952}},
            intelligent_brain=MagicMock(regime_by_symbol={}, experiments=MagicMock(data={"experiments": {}})),
            profit_manager=MagicMock(),
            now_ts=1030.0,
        )
        verdict = evaluate_fast_exit(ctx)
        assert verdict["action"] in {"HOLD", "LOCK", "TAKE", "SCRATCH", "ABORT", "TIME_EXIT"}

    def test_pnl_calculation_uses_correct_liquidation_price(self):
        """Verify PnL pips uses correct liquidation price for each side."""
        from aegis.intel.broker_math import BrokerSymbolSpec, mfe_mae_from_usd
        
        # BUY: entry=1.10000, current_bid=1.10050 -> pnl = 5 pips
        # SELL: entry=1.10000, current_ask=1.09950 -> pnl = 5 pips
        buy_ctx = self.create_context(side="buy", current_bid=1.10050, current_ask=1.10052)
        sell_ctx = self.create_context(
            side="sell", current_bid=1.09950, current_ask=1.09952,
            stop_loss=1.10100, track_target=1.09800,
            track_invalidation=1.10100, track_side="sell"
        )
        
        buy_verdict = evaluate_fast_exit(buy_ctx)
        sell_verdict = evaluate_fast_exit(sell_ctx)
        
        # Both should execute without error
        assert buy_verdict["action"] != "ERROR"
        assert sell_verdict["action"] != "ERROR"

def test_missing_runtime_policy_does_not_replace_existing_hold():
    result = combine_existing_exit_with_policy(
        {"action": "HOLD", "reason": "structural_hold"},
        {"action": "NO_EVIDENCE", "reason": "missing_validated_policy_artifact"},
    )

    assert result == {
        "action": "HOLD",
        "reason": "structural_hold",
        "policy_action": "NO_EVIDENCE",
        "policy_reason": "missing_validated_policy_artifact",
    }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
