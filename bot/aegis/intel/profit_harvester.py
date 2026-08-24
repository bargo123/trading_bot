"""Pure, evidence-gated normalized decisions for Firehose profit harvesting."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class HarvestPolicyEvidence:
    """The minimum complete, costed OOS evidence required to activate a policy."""

    policy_id: str
    status: str
    completed_lifecycles: int
    oos_expectancy_after_cost: float | None

    @property
    def is_complete(self) -> bool:
        return (
            bool(self.policy_id)
            and self.status == "COMPLETE"
            and self.completed_lifecycles > 0
            and _is_finite(self.oos_expectancy_after_cost)
        )


@dataclass(frozen=True)
class HarvestPolicy:
    """Evidence-selected normalized thresholds; never USD profit targets."""

    min_net_r: float
    min_mfe_r: float
    protected_mfe_fraction: float
    max_extension_s: float
    scratch_age_s: float
    scratch_loss_r: float
    stalled_return_r: float
    accelerating_return_r: float
    evidence: HarvestPolicyEvidence | None

    @property
    def is_available(self) -> bool:
        return (
            self.evidence is not None
            and self.evidence.is_complete
            and all(_is_finite(value) for value in (
                self.min_net_r,
                self.min_mfe_r,
                self.protected_mfe_fraction,
                self.max_extension_s,
                self.scratch_age_s,
                self.scratch_loss_r,
                self.stalled_return_r,
                self.accelerating_return_r,
            ))
            and self.min_net_r >= 0
            and self.min_mfe_r > 0
            and 0 < self.protected_mfe_fraction <= 1
            and self.max_extension_s >= 0
            and self.scratch_age_s >= 0
            and self.scratch_loss_r < 0
            and self.stalled_return_r >= 0
            and self.accelerating_return_r > self.stalled_return_r
        )


@dataclass(frozen=True)
class HarvestInput:
    ticket: str
    side: str
    net_pnl_r: float | None
    mfe_r: float | None
    age_s: float | None
    return_5s_r: float | None
    return_15s_r: float | None
    return_30s_r: float | None
    remaining_ev: float | None
    remaining_ev_status: str
    spread_normal: bool | None
    observed_spread_r: float | None
    observed_slippage_r: float | None
    observed_commission_r: float | None

    @property
    def has_required_evidence(self) -> bool:
        return (
            bool(self.ticket)
            and self.side in {"buy", "sell"}
            and self.remaining_ev_status == "ESTIMATED"
            and self.spread_normal is not None
            and all(_is_finite(value) for value in (
                self.net_pnl_r,
                self.mfe_r,
                self.age_s,
                self.return_5s_r,
                self.return_15s_r,
                self.return_30s_r,
                self.remaining_ev,
                self.observed_spread_r,
                self.observed_slippage_r,
                self.observed_commission_r,
            ))
        )


@dataclass(frozen=True)
class HarvestDecision:
    action: str
    reason: str


class ProfitHarvester:
    """Evaluate an explicit, complete policy without mutating trade state."""

    def __init__(self, policy: HarvestPolicy | None):
        self.policy = policy

    def evaluate(self, input: HarvestInput) -> HarvestDecision:
        if self.policy is None or not self.policy.is_available:
            return HarvestDecision("UNAVAILABLE", "harvest_policy_unavailable")
        if input.remaining_ev_status == "ESTIMATED" and not _is_finite(input.remaining_ev):
            return HarvestDecision("ABORT", "remaining_ev_invalid")
        if not input.has_required_evidence:
            return HarvestDecision("UNAVAILABLE", "harvest_evidence_unavailable")

        policy = self.policy
        if input.remaining_ev <= 0:
            return HarvestDecision("ABORT", "remaining_ev_negative")
        if (
            input.mfe_r >= policy.min_mfe_r
            and input.net_pnl_r < input.mfe_r * policy.protected_mfe_fraction
        ):
            return HarvestDecision("QUICK_TAKE", "profit_floor_breach")
        if (
            input.net_pnl_r >= policy.min_net_r
            and input.mfe_r >= policy.min_mfe_r
            and self._momentum_stalled(input)
        ):
            return HarvestDecision("QUICK_TAKE", "momentum_stall_profit_harvest")
        if self._can_extend(input):
            return HarvestDecision("MOMENTUM_HOLD", "bounded_favorable_momentum")
        if (
            input.age_s <= policy.scratch_age_s
            and input.net_pnl_r <= policy.scratch_loss_r
            and input.mfe_r < policy.min_mfe_r
            and input.return_5s_r < 0
        ):
            return HarvestDecision("SCRATCH", "early_no_progress_adverse")
        return HarvestDecision("UNAVAILABLE", "harvest_no_supported_action")

    def _momentum_stalled(self, input: HarvestInput) -> bool:
        assert self.policy is not None
        return (
            input.return_5s_r <= self.policy.stalled_return_r
            or input.return_5s_r < input.return_15s_r < input.return_30s_r
        )

    def _can_extend(self, input: HarvestInput) -> bool:
        assert self.policy is not None
        return (
            input.age_s <= self.policy.max_extension_s
            and input.spread_normal is True
            and input.net_pnl_r == input.mfe_r
            and input.return_5s_r >= self.policy.accelerating_return_r
            and input.return_5s_r > input.return_15s_r > input.return_30s_r > 0
        )


def _is_finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
