"""Frozen validated strategy model consumed by the firehose runtime.

Promotion happens in research. This module only checks whether a frozen
artifact is allowed to be inherited by a runtime thesis.
It must never import the research package.
"""
from __future__ import annotations

from dataclasses import dataclass

from aegis.intel.expected_value import MAX_WINS_ERASED_BY_AVERAGE_LOSS

MIN_STRATEGY_TRADES = 20
MIN_STRATEGY_LOSSES = 5

# Explicit governance ladder. A model may only act on the market at the stage
# its evidence supports; a research bootstrap can never behave like a champion.
STAGE_UNVALIDATED_RESEARCH = "UNVALIDATED_RESEARCH"
STAGE_SHADOW = "SHADOW"
STAGE_DEMO_CANARY = "DEMO_CANARY"
STAGE_DEMO_CHAMPION = "DEMO_CHAMPION"
GOVERNANCE_STAGES = (
    STAGE_UNVALIDATED_RESEARCH,
    STAGE_SHADOW,
    STAGE_DEMO_CANARY,
    STAGE_DEMO_CHAMPION,
)
# Stages allowed to send demo orders (never live - the runner enforces that
# separately). Research/shadow models decide but do not trade.
TRADING_STAGES = frozenset({STAGE_DEMO_CANARY, STAGE_DEMO_CHAMPION})


@dataclass(frozen=True)
class ValidatedStrategyModel:
    strategy_id: str
    promoted: bool
    n_trades: int
    n_losses: int
    expectancy: float
    profit_factor: float
    bootstrap_p05: float
    wins_erased_by_average_loss: float
    wins_erased_by_tail_loss: float
    validated_risk_fraction: float | None
    artifact_hash: str
    allowed_states: frozenset[frozenset[str]] = frozenset()
    promotion_stage: str = STAGE_DEMO_CHAMPION
    dataset_hash: str = ""
    validation_hash: str = ""

    @property
    def may_trade(self) -> bool:
        return self.promoted and self.promotion_stage in TRADING_STAGES


def strategy_model_ready(model: ValidatedStrategyModel) -> tuple[bool, str]:
    """Strategy/challenger promotion requires sample size AND a sampled loss tail."""
    if not model.promoted:
        return False, "no_validated_strategy_model"
    if model.promotion_stage not in GOVERNANCE_STAGES:
        return False, f"unknown_promotion_stage:{model.promotion_stage}"
    if int(model.n_trades) < MIN_STRATEGY_TRADES:
        return False, f"insufficient_sample: n_trades={int(model.n_trades)}"
    if int(model.n_losses) < MIN_STRATEGY_LOSSES:
        return False, f"insufficient_loss_tail: n_losses={int(model.n_losses)}"
    if float(model.expectancy) <= 0:
        return False, "strategy_expectancy_not_positive"
    if float(model.profit_factor) <= 1:
        return False, "strategy_profit_factor_not_above_one"
    if float(model.bootstrap_p05) <= 0:
        return False, "strategy_bootstrap_tail_not_positive"
    if float(model.wins_erased_by_average_loss) >= MAX_WINS_ERASED_BY_AVERAGE_LOSS:
        return False, (
            "destructive_payoff_asymmetry: "
            f"wins_erased_by_average_loss={float(model.wins_erased_by_average_loss)}"
        )
    if model.validated_risk_fraction is None or not 0 < float(model.validated_risk_fraction) <= 1:
        return False, "no_validated_risk_fraction"
    return True, "ok"
