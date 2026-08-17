"""Shadow intelligence cycle: observe, explain, and persist; never trade."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping, Sequence

import pandas as pd

from aegis.intel.expected_value import payoff_metrics
from aegis.intel.strategy_model import ValidatedStrategyModel
from aegis.intel.thesis_fire import evaluate_thesis_action, evaluate_thesis_fire
from aegis.research.books_index import BookIndex
from aegis.research.fingerprint import dataset_fingerprint
from aegis.research.intelligence import form_research_thesis
from aegis.research.learning import attribute_outcomes, slice_outcomes
from aegis.research.market_state import build_market_state
from aegis.research.registry import DuplicateExperimentError, ExperimentRegistry
from aegis.research.thesis import (
    explain_thesis,
    target_thesis_exposure,
    thesis_experiment_row,
    thesis_information_id,
)


def run_intelligence_cycle(
    *,
    thesis_id: str,
    symbol: str,
    side: str,
    setup: str,
    m1: pd.DataFrame,
    historical_outcomes: Sequence[float],
    book_query: str,
    invalidation: str,
    expected_duration: str,
    index: BookIndex,
    registry: ExperimentRegistry,
    execution: Mapping[str, Any] | None = None,
    portfolio: Mapping[str, Any] | None = None,
    current_risk_usd: float = 0.0,
    correlated_risk_usd: float = 0.0,
    total_risk_budget_usd: float = 0.0,
    validated_risk_fraction: float | None = None,
    outcome_rows: Sequence[Mapping[str, Any]] = (),
    outcome_scope: str = "unattributed",
    strategy: ValidatedStrategyModel | None = None,
    portfolio_ok: bool = True,
    portfolio_reason: str = "",
    last_information_id: str | None = None,
    invalidated: bool = False,
) -> dict[str, Any]:
    """Run a non-mutating research cycle and append its explainable result."""
    state = build_market_state(
        symbol=symbol,
        m1=m1,
        execution=execution,
        portfolio=portfolio,
        provenance={"cycle": "intelligence_shadow.v1"},
    )
    thesis = form_research_thesis(
        thesis_id=thesis_id,
        symbol=symbol,
        side=side,
        setup=setup,
        state=state,
        historical_outcomes=historical_outcomes,
        book_query=book_query,
        index=index,
        invalidation=invalidation,
        expected_duration=expected_duration,
        outcome_scope=outcome_scope,
    )
    exposure = target_thesis_exposure(
        thesis=thesis,
        current_risk_usd=current_risk_usd,
        correlated_risk_usd=correlated_risk_usd,
        total_risk_budget_usd=total_risk_budget_usd,
        validated_risk_fraction=validated_risk_fraction,
    )
    dataset_fp = dataset_fingerprint(m1)
    status = "open" if thesis.calibrated_evidence.eligible else "rejected"
    reason = None if status == "open" else thesis.calibrated_evidence.uncertainty
    row = thesis_experiment_row(
        thesis=thesis,
        dataset_fingerprint=dataset_fp,
        status=status,
        rejection_reason=reason,
    )
    try:
        registry.record(row)
        recorded = True
    except DuplicateExperimentError:
        recorded = False
    if outcome_scope == "state_matched":
        payoff = payoff_metrics(historical_outcomes)
        analogue_n = int(payoff["n"])
        analogue_n_losses = int(payoff["n_losses"])
        state_ev = payoff["expectancy"]
    else:
        analogue_n = 0
        analogue_n_losses = 0
        state_ev = None
    fire = evaluate_thesis_fire(
        strategy=strategy,
        state_expected_net_value=state_ev,
        analogue_n=analogue_n,
        analogue_n_losses=analogue_n_losses,
        uncertainty=thesis.calibrated_evidence.uncertainty,
        eligible=thesis.calibrated_evidence.eligible,
        portfolio_ok=portfolio_ok,
        portfolio_reason=portfolio_reason,
    )
    info_id = thesis_information_id(
        symbol=symbol,
        side=side,
        setup=setup,
        invalidation=invalidation,
        htf_bucket=str((state.multi_timeframe.get("H1") or {}).get("time") or ""),
        session=str(state.session or ""),
    )
    action = evaluate_thesis_action(
        fire_decision=fire,
        information_id=info_id,
        last_information_id=last_information_id,
        current_risk_usd=current_risk_usd,
        target_risk_usd=exposure.target_risk_usd,
        invalidated=invalidated,
    )
    attribution_rows = list(outcome_rows) or [
        {"thesis_id": thesis_id, "pnl": value, "symbol": symbol, "side": side}
        for value in historical_outcomes
    ]
    return {
        "schema": "intelligence_cycle.v1",
        "label": "research_proxy",
        "placed_orders": False,
        "mt5_touched": False,
        "promoted_live_yaml": False,
        "recorded": recorded,
        "state": state.as_dict(),
        "thesis": thesis.as_dict(),
        "exposure": asdict(exposure),
        "fire_decision": {
            "action": action.action,
            "reason": action.reason,
            "expected_net_value": action.expected_net_value,
            "inherited_strategy": None if strategy is None else strategy.strategy_id,
            "information_id": info_id,
        },
        "explanation": explain_thesis(thesis, exposure),
        "attribution": attribute_outcomes(attribution_rows),
        "slices": slice_outcomes(attribution_rows),
    }


def intelligence_cycle_markdown(result: Mapping[str, Any]) -> str:
    """Stable explanation artifact for research reports."""
    state = result["state"]
    exposure = result["exposure"]
    attribution = result["attribution"]
    return "\n".join(
        [
            "# Intelligence shadow cycle",
            "",
            "Label: `research_proxy`. No orders placed; no live YAML promotion.",
            "",
            "```text",
            str(result["explanation"]),
            "```",
            "",
            "## Market state",
            "",
            f"- observed_at: {state['observed_at']}",
            f"- regime: {state['regime'].get('label')}",
            f"- htf_ready: {state.get('htf_ready')}",
            f"- session: {state.get('session')}",
            f"- volatility: {state['volatility'].get('phase')}",
            "",
            "## Exposure",
            "",
            f"- action: {exposure['action']}",
            f"- reason: {exposure['reason']}",
            f"- target risk USD: {exposure['target_risk_usd']}",
            "",
            "## Fire decision (shadow; no orders)",
            "",
            f"- action: {result['fire_decision']['action']}",
            f"- reason: {result['fire_decision']['reason']}",
            f"- inherited strategy: {result['fire_decision']['inherited_strategy'] or 'none'}",
            "",
            "## Outcome learning",
            "",
            f"- thesis clusters: {len(attribution)}",
            f"- registry row recorded: {result['recorded']}",
            "",
        ]
    )
