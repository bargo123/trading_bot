"""Behavioral tests for the evidence-gated normalized profit harvester."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aegis.intel.profit_harvester import (  # noqa: E402
    HarvestInput,
    HarvestPolicy,
    HarvestPolicyEvidence,
    ProfitHarvester,
)


def _policy(*, status: str = "COMPLETE") -> HarvestPolicy:
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
            policy_id="oos-costed-firehose-v1",
            status=status,
            completed_lifecycles=12,
            oos_expectancy_after_cost=0.08,
        ),
    )


def _observed_state(**overrides: object) -> HarvestInput:
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


def test_cost_adjusted_profitable_stall_quick_takes():
    """A stall branch must close a cost-observed meaningful winner."""
    decision = ProfitHarvester(_policy()).evaluate(_observed_state())

    assert decision.action == "QUICK_TAKE"
    assert decision.reason == "momentum_stall_profit_harvest"


def test_accelerating_winner_gets_bounded_momentum_hold():
    """A favorable accelerating winner must retain its bounded extension."""
    decision = ProfitHarvester(_policy()).evaluate(_observed_state(
        gross_pnl_r=0.84,
        gross_mfe_r=0.84,
        gross_return_5s_r=0.13,
        gross_return_15s_r=0.11,
        gross_return_30s_r=0.09,
    ))

    assert decision.action == "MOMENTUM_HOLD"


def test_floor_breach_takes_before_normal_loss():
    """An armed R-based floor must prevent a winner degrading into a loss."""
    decision = ProfitHarvester(_policy()).evaluate(_observed_state(
        gross_mfe_r=1.04,
        gross_pnl_r=0.49,
    ))

    assert decision.action == "QUICK_TAKE"
    assert decision.reason == "profit_floor_breach"


def test_negative_remaining_ev_aborts():
    """An observed negative remaining EV must invalidate the position."""
    assert ProfitHarvester(_policy()).evaluate(_observed_state(
        remaining_ev=-0.01,
    )).action == "ABORT"


def test_no_progress_loser_scratches_before_protective_stop():
    """An early adverse no-progress trade must scratch before a full stop."""
    assert ProfitHarvester(_policy()).evaluate(_observed_state(
        gross_pnl_r=-0.26,
        gross_mfe_r=0.09,
        age_s=10.0,
        gross_return_5s_r=0.00,
        gross_return_15s_r=0.01,
        gross_return_30s_r=0.02,
    )).action == "SCRATCH"


def test_missing_cost_or_momentum_evidence_is_unavailable():
    """Missing observations must not invent a harvest decision."""
    assert ProfitHarvester(_policy()).evaluate(_observed_state(
        gross_return_5s_r=None,
    )).action == "UNAVAILABLE"


def test_observed_costs_can_remove_gross_winner_take_eligibility():
    """Dropping cost subtraction must not let gross PnL qualify as net profit."""
    harvester = ProfitHarvester(_policy())
    gross_winner = _observed_state(gross_pnl_r=0.54, gross_mfe_r=0.70)
    higher_cost = _observed_state(
        gross_pnl_r=0.54,
        gross_mfe_r=0.70,
        observed_commission_r=0.05,
    )

    assert gross_winner.net_pnl_r == 0.50
    assert harvester.evaluate(gross_winner).action == "QUICK_TAKE"
    assert harvester.evaluate(higher_cost).action == "UNAVAILABLE"


def test_near_peak_net_pnl_uses_normalized_no_giveback_tolerance():
    """Replacing tolerance with exact equality must not deny a valid extension."""
    decision = ProfitHarvester(_policy()).evaluate(_observed_state(
        gross_pnl_r=0.8399995,
        gross_mfe_r=0.84,
        gross_return_5s_r=0.13,
        gross_return_15s_r=0.11,
        gross_return_30s_r=0.09,
    ))

    assert decision.action == "MOMENTUM_HOLD"


def test_absent_or_incomplete_policy_artifact_is_unavailable():
    """Policy activation requires a complete, finite costed OOS artifact."""
    observed = _observed_state()

    assert ProfitHarvester(None).evaluate(observed).action == "UNAVAILABLE"
    assert ProfitHarvester(_policy(status="NO_EVIDENCE")).evaluate(observed).action == "UNAVAILABLE"
    assert ProfitHarvester(HarvestPolicy(
        min_net_r=0.50,
        min_mfe_r=0.60,
        protected_mfe_fraction=0.60,
        max_extension_s=30.0,
        scratch_age_s=20.0,
        scratch_loss_r=-0.25,
        stalled_return_r=0.02,
        accelerating_return_r=0.05,
        evidence=HarvestPolicyEvidence(
            policy_id="invalid-oos-costed-firehose-v1",
            status="COMPLETE",
            completed_lifecycles=12,
            oos_expectancy_after_cost=math.nan,
        ),
    )).evaluate(observed).action == "UNAVAILABLE"
