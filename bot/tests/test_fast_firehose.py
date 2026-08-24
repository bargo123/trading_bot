"""FAST_TURNOVER_FIREHOSE_V1 tests (spec phases 3-9, 11-12)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.intel.fast_firehose import (  # noqa: E402
    ExitAction,
    FastExitConfig,
    FastExitStateMachine,
    FastMarketContext,
    MicroCandidate,
    check_entry_economics,
    classify_firehose_mode,
    diagnose_micro_candidates,
    generate_micro_candidates,
    micro_momentum_burst,
    failed_breakout_fade,
    fair_value_snapback,
    pip_value,
)
from aegis.intel.profit_harvester import (  # noqa: E402
    HarvestDecision,
    HarvestInput,
    HarvestPolicy,
    HarvestPolicyEvidence,
)


def _ctx(**overrides) -> FastMarketContext:
    """Build a test FastMarketContext with reasonable defaults."""
    base = dict(
        symbol="EURUSD", timestamp="2026-08-21T12:00:00Z",
        bid=1.1000, ask=1.10002, spread_pips=0.2,
        m1_open=1.09998, m1_high=1.10008, m1_low=1.09990,
        m1_close=1.10000, m1_prev_close=1.09995, m1_atr=0.0015,
        m1_range=0.00018, m1_body=0.00005, m1_volume=100,
        m5_compression=0.4,
        m5_direction="up", m5_structure="none",
        m5_support=1.0950, m5_resistance=1.1050, m5_atr=0.002,
        m15_direction="up", m15_structure="none",
        m15_support=1.0950, m15_resistance=1.1050,
        m15_range_mid=1.1000, m15_range_half_width=0.0040,
        return_30s_buy=0.0008, return_30s_sell=-0.0008,
        return_15s_buy=0.0004, return_15s_sell=-0.0004,
        return_60s_buy=0.001, return_60s_sell=-0.001,
        session="london", regime="trend",
    )
    base.update(overrides)
    return FastMarketContext(**base)


def test_pip_value_jpy_vs_standard():
    assert pip_value("EURUSD") == 0.0001
    assert pip_value("USDJPY") == 0.01
    assert pip_value("GBPUSD") == 0.0001
    assert pip_value("XAUUSD") == 0.1


def test_micro_momentum_burst_generates_on_compression_release():
    c = micro_momentum_burst(_ctx(
        m15_direction="up", m5_direction="up",
        return_30s_buy=0.0008, return_30s_sell=-0.0008,
        m1_atr=0.0015,
        m1_low=1.0998, m1_high=1.1001, spread_pips=0.2))
    assert c is not None
    assert c.family == "micro_momentum_burst"
    assert c.side == "buy"
    assert c.max_hold_s <= 180


def test_micro_momentum_rejects_when_no_impulse():
    c = micro_momentum_burst(_ctx(
        m15_direction="up", m5_direction="up",
        return_30s_buy=0.00001, return_30s_sell=-0.00001,
        m1_atr=0.0015,
        m1_low=1.0998, m1_high=1.1001, spread_pips=0.2))
    assert c is None


def test_failed_breakout_fade_generates_on_trap():
    c = failed_breakout_fade(_ctx(
        regime="range", session="london",
        m15_resistance=1.2750, m15_support=1.2700,
        m1_close=1.2748, m1_prev_close=1.2752,
        bid=1.2747, ask=1.2749, m1_atr=0.0020,
        m1_low=1.2740, m1_high=1.2755, spread_pips=0.3))
    assert c is not None
    assert c.side == "sell"


def test_fair_value_snapback_generates_at_range_edge():
    c = fair_value_snapback(_ctx(
        regime="range", session="asia",
        m15_range_mid=0.6500, m15_range_half_width=0.0030,
        m1_close=0.6535, m1_atr=0.0015,
        bid=0.6534, ask=0.6536, spread_pips=0.2))
    assert c is not None
    assert c.side == "sell"
    assert c.required_regime == "range"


def test_generate_multiple_independent_candidates():
    """Multiple families can produce candidates simultaneously."""
    results = generate_micro_candidates(_ctx(
        regime="range", session="asia",
        m15_direction="down", m5_direction="down",
        m15_resistance=1.1050, m15_support=1.0950,
        m15_range_mid=1.1000, m15_range_half_width=0.0040,
        m1_close=1.1042, m1_prev_close=1.1052,
        m1_low=1.1028, m1_high=1.1053,
        m1_atr=0.0020, return_30s_sell=-0.0012, return_30s_buy=0.0012,
        bid=1.1041, ask=1.1043, spread_pips=0.2))
    families = {c.family for c in results}
    assert len(families) >= 2, f"expected multiple families, got: {families}"


def test_micro_diagnostics_identify_missing_return_without_candidate():
    candidates, reasons = diagnose_micro_candidates(_ctx(
        return_30s_buy=None,
        return_30s_sell=None,
    ))

    assert candidates == []
    assert reasons["micro_momentum_burst"] == "missing_return_30s"


def test_micro_diagnostics_identify_missing_m15_range():
    _, reasons = diagnose_micro_candidates(_ctx(
        m15_range_mid=None,
        m15_range_half_width=None,
    ))

    assert reasons["fair_value_snapback"] == "missing_m15_range"


def test_entry_economics_blocks_min_lot_risk_exceeding_budget():
    """Spec P6/audit defect 1: broker min lot risk > budget = BLOCKED."""
    cand = MicroCandidate(
        hypothesis_id="h1", family="test", symbol="EURUSD", side="buy",
        entry_price=1.10, invalidation=1.0950, target=1.1050,
        max_hold_s=60, required_regime="trend", required_session="asia",
        spread_pips=1.0, stop_pips=50, target_pips=50,
        risk_usd_min_lot=5.0, lane="SHADOW", mechanism="test")
    result = check_entry_economics(cand, max_risk_usd=0.15)
    assert not result["allowed"]
    assert "RISK_GRANULARITY_BLOCKED" in result["rejections"]


def test_entry_economics_blocks_negative_net_target():
    cand = MicroCandidate(
        hypothesis_id="h2", family="test", symbol="EURUSD", side="buy",
        entry_price=1.10, invalidation=1.0999, target=1.1001,
        max_hold_s=60, required_regime="trend", required_session="asia",
        spread_pips=2.0, stop_pips=1, target_pips=1,
        risk_usd_min_lot=0.05, lane="SHADOW", mechanism="test")
    result = check_entry_economics(cand, max_risk_usd=0.15)
    assert "NEGATIVE_EXPECTED_NET_AFTER_COST" in result["rejections"]


# ---------------------------------------------------------------------------
# Fast exit state machine
# ---------------------------------------------------------------------------


def _sm(**cfg):
    return FastExitStateMachine(FastExitConfig(**cfg))


BASE = dict(side="buy", entry_price=1.1000, stop_loss=1.0990,
            stop_pips=10, pip=0.0001)


def _harvest_policy(*, status="COMPLETE"):
    return HarvestPolicy(
        min_net_r=0.50, min_mfe_r=0.60, protected_mfe_fraction=0.60,
        max_extension_s=30.0, scratch_age_s=20.0, scratch_loss_r=-0.25,
        stalled_return_r=0.02, accelerating_return_r=0.05,
        evidence=HarvestPolicyEvidence(
            policy_id="costed-oos-v1", status=status,
            completed_lifecycles=12, oos_expectancy_after_cost=0.08,
        ),
    )


def _harvest_input(**overrides):
    values = {
        "ticket": "T1", "side": "buy", "gross_pnl_r": 0.74,
        "gross_mfe_r": 0.84, "age_s": 10.0,
        "gross_return_5s_r": 0.05, "gross_return_15s_r": 0.07,
        "gross_return_30s_r": 0.09, "remaining_ev": 0.04,
        "remaining_ev_status": "ESTIMATED", "spread_normal": True,
        "observed_spread_r": 0.02, "observed_slippage_r": 0.01,
        "observed_commission_r": 0.01,
    }
    values.update(overrides)
    return HarvestInput(**values)


def test_fast_exit_take_at_target():
    sm = _sm()
    v = sm.evaluate(
        side="buy", entry_price=1.1000, current_mark=1.10199,
        stop_loss=1.0990, target=1.1020,
        opened_ts=1000, now=1030, pnl_pips=19.9,
        mfe_pips=20, mae_pips=-1,
        stop_pips=10, pip=0.0001)
    assert v["action"] == "TAKE"


def test_fast_exit_lock_after_mfe_arm():
    sm = _sm()
    v = sm.evaluate(
        side="buy", entry_price=1.1000, current_mark=1.1006,
        stop_loss=1.0990, target=1.1020, opened_ts=1000, now=1030,
        pnl_pips=6.0, mfe_pips=7.0, mae_pips=-1.0,
        stop_pips=10, pip=0.0001)
    assert v["action"] == "LOCK"
    assert "cost-plus lock" in v["why"] or "armed" in v["why"]


def test_fast_exit_scratch_on_time_decay_without_progress():
    sm = _sm(time_exit_s=120)
    v = sm.evaluate(
        side="buy", entry_price=1.1000, current_mark=1.10001,
        stop_loss=1.0990, target=1.1020, opened_ts=1000, now=1300,
        pnl_pips=0.1, mfe_pips=0.3, mae_pips=-0.5,
        stop_pips=10, pip=0.0001)
    assert v["action"] == "SCRATCH"


def test_fast_exit_abort_on_regime_change_losing():
    sm = _sm()
    v = sm.evaluate(
        side="buy", entry_price=1.1000, current_mark=1.0998,
        stop_loss=1.0990, target=1.1020, opened_ts=1000, now=1020,
        pnl_pips=-2.0, mfe_pips=0.5, mae_pips=-3.0,
        stop_pips=10, pip=0.0001,
        regime_now="range", regime_at_entry="trend")
    assert v["action"] == "ABORT"
    assert "regime" in v["why"]


def test_fast_exit_hold_with_positive_ev():
    sm = _sm()
    v = sm.evaluate(
        side="buy", entry_price=1.1000, current_mark=1.1003,
        stop_loss=1.0990, target=1.1020, opened_ts=1000, now=1020,
        pnl_pips=3.0, mfe_pips=3.5, mae_pips=-0.5,
        stop_pips=10, pip=0.0001,
        remaining_ev=0.03, remaining_ev_status="ESTIMATED")
    assert v["action"] == "HOLD"
    assert "positive" in v["why"].lower() or "mfe" in v["why"].lower()


def test_fast_exit_legacy_target_take_behavior_is_unchanged():
    """A structural target must remain higher priority than a harvest hint."""
    v = _sm().evaluate(
        side="buy", entry_price=1.1000, current_mark=1.10199,
        stop_loss=1.0990, target=1.1020,
        opened_ts=1000, now=1030, pnl_pips=19.9,
        mfe_pips=20, mae_pips=-1,
        stop_pips=10, pip=0.0001,
        harvest_decision=HarvestDecision("MOMENTUM_HOLD", "bounded_favorable_momentum"),
    )

    assert v["action"] == "TAKE"
    assert v["reason"] == "target_reached"


def test_fast_exit_maps_quick_take_after_existing_protections():
    """A validated harvest close must replace only the legacy default HOLD."""
    v = _sm().evaluate(
        side="buy", entry_price=1.1000, current_mark=1.1003,
        stop_loss=1.0990, target=1.1020,
        opened_ts=1000, now=1020, pnl_pips=3.0,
        mfe_pips=3.0, mae_pips=-0.5,
        stop_pips=10, pip=0.0001,
        remaining_ev=0.03, remaining_ev_status="ESTIMATED",
        harvest_policy=_harvest_policy(),
        harvest_input=_harvest_input(),
    )

    assert v["action"] == "QUICK_TAKE"
    assert v["reason"] == "momentum_stall_profit_harvest"


def test_fast_exit_ignores_injected_quick_take_without_evidence_artifact():
    """Removing policy validation must not let an injected close bypass HOLD."""
    v = _sm().evaluate(
        side="buy", entry_price=1.1000, current_mark=1.1003,
        stop_loss=1.0990, target=1.1020,
        opened_ts=1000, now=1020, pnl_pips=3.0,
        mfe_pips=3.0, mae_pips=-0.5,
        stop_pips=10, pip=0.0001,
        remaining_ev=0.03, remaining_ev_status="ESTIMATED",
        harvest_decision=HarvestDecision("QUICK_TAKE", "injected"),
    )

    assert v["action"] == "HOLD"
    assert v["reason"] == "fast_hold_justified"


def test_fast_exit_uses_harvester_only_with_complete_policy_artifact():
    """An evaluated, artifact-backed quick take may replace the legacy hold."""
    v = _sm().evaluate(
        side="buy", entry_price=1.1000, current_mark=1.1003,
        stop_loss=1.0990, target=1.1020,
        opened_ts=1000, now=1020, pnl_pips=3.0,
        mfe_pips=3.0, mae_pips=-0.5,
        stop_pips=10, pip=0.0001,
        remaining_ev=0.03, remaining_ev_status="ESTIMATED",
        harvest_policy=_harvest_policy(),
        harvest_input=_harvest_input(),
    )

    assert v["action"] == "QUICK_TAKE"
    assert v["reason"] == "momentum_stall_profit_harvest"


def test_fast_exit_honors_harvest_floor_breach_before_legacy_lock():
    """An armed floor breach must close rather than merely adjust the stop."""
    v = _sm(giveback_frac=0.70).evaluate(
        side="buy", entry_price=1.1000, current_mark=1.10045,
        stop_loss=1.0990, target=1.1020,
        opened_ts=1000, now=1020, pnl_pips=4.5,
        mfe_pips=10.0, mae_pips=-0.5,
        stop_pips=10, pip=0.0001,
        remaining_ev=0.03, remaining_ev_status="ESTIMATED",
        harvest_policy=_harvest_policy(),
        harvest_input=_harvest_input(gross_pnl_r=0.49, gross_mfe_r=1.04),
    )

    assert v["action"] == "QUICK_TAKE"
    assert v["reason"] == "profit_floor_breach"


def test_one_large_loser_cannot_occur_from_old_geometry():
    """The old 30-pip fallback must never produce a valid exploration order."""
    from aegis.intel.exploration import risk_lots_for_exploration

    r = risk_lots_for_exploration(
        max_risk_usd=0.15, entry=1.10, invalidation=1.07,
        pip=0.0001, contract_size=100000.0,
        volume_min=0.01, volume_step=0.01)
    assert r["allowed"] is False


# ---------------------------------------------------------------------------
# Firehose mode classification (Phase 12)
# ---------------------------------------------------------------------------


def test_firehose_mode_classification():
    assert classify_firehose_mode(broker_round_trips=5, shadow_trades=100) == \
        "DEMO_FAST_TURNOVER_FIREHOSE"
    assert classify_firehose_mode(broker_round_trips=0, shadow_trades=500) == \
        "SHADOW_RESEARCH_FIREHOSE"
    assert classify_firehose_mode(broker_round_trips=0, shadow_trades=0) == \
        "RESEARCH_CANDIDATES_ONLY"
