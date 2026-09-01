"""Runtime FIRE/SKIP/SCALE/REDUCE/EXIT for one thesis. Deterministic; no LLM; no research import.

A thesis inherits a validated strategy model, then still has to prove
state-specific edge, analogue evidence, calibrated uncertainty, and portfolio room.
Scale only on a new information_id. Duplicate prints are redundant, not confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass

from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready

MIN_ANALOGUE_N = 20
THESIS_ACTIONS = frozenset({"fire", "skip", "scale", "reduce", "exit"})
# Reasons that mean the ENTRY case is gone. For a FLAT thesis they block entry;
# for an OPEN thesis they are NOT exits: an open position must not be closed
# merely because the current bar no longer matches the entry allowlist.
ENTRY_GATE_REASONS = frozenset(
    {
        "state_not_in_validated_set",
        "no_validated_strategy_model",
        "unacceptable_uncertainty",
        "insufficient_analogue_evidence",
    }
)
# A measured negative state expectancy is material evidence AGAINST an open
# thesis: it justifies REDUCE (de-risk), never a silent full EXIT by itself.
EDGE_GONE_REASONS = frozenset(
    {
        "state_ev_not_positive",
        "strategy_expectancy_not_positive",
        "strategy_profit_factor_not_above_one",
        "strategy_bootstrap_tail_not_positive",
    }
)


@dataclass(frozen=True)
class ThesisFireDecision:
    action: str
    reason: str
    expected_net_value: float | None = None


def evaluate_thesis_fire(
    *,
    strategy: ValidatedStrategyModel | None,
    state_expected_net_value: float | None,
    analogue_n: int,
    analogue_n_losses: int = 0,
    uncertainty: str,
    eligible: bool,
    portfolio_ok: bool,
    portfolio_reason: str = "",
) -> ThesisFireDecision:
    """Skip fast unless every inherited-model + state gate passes. Fire immediately if they do."""
    if strategy is None:
        return ThesisFireDecision("skip", "no_validated_strategy_model")
    ready, ready_reason = strategy_model_ready(strategy)
    if not ready:
        return ThesisFireDecision("skip", ready_reason)
    if not eligible or str(uncertainty) != "calibrated":
        return ThesisFireDecision("skip", "unacceptable_uncertainty")
    if int(analogue_n) < MIN_ANALOGUE_N:
        return ThesisFireDecision("skip", "insufficient_analogue_evidence")
    if state_expected_net_value is None or float(state_expected_net_value) <= 0:
        return ThesisFireDecision("skip", "state_ev_not_positive")
    if not portfolio_ok:
        return ThesisFireDecision("skip", portfolio_reason or "portfolio_risk")
    return ThesisFireDecision(
        "fire",
        "positive_state_ev_on_validated_strategy",
        float(state_expected_net_value),
    )


def evaluate_thesis_action(
    *,
    fire_decision: ThesisFireDecision,
    information_id: str,
    last_information_id: str | None,
    current_risk_usd: float,
    target_risk_usd: float,
    invalidated: bool,
    target_reached: bool = False,
    opposite_side: bool = False,
) -> ThesisFireDecision:
    """Map fire/skip plus exposure and invalidation onto one firehose action.

    ENTRY and HOLD/EXIT are different decisions:
      - FLAT + entry gate fails            -> skip (no new exposure)
      - OPEN + entry gate fails            -> hold (entry allowlist is not an
        exit rule; the position keeps its protective stop)
      - OPEN + structural invalidation /
        target reached / opposite thesis   -> exit
      - OPEN + measured negative state EV  -> reduce (de-risk, not full exit)
      - OPEN + new independent evidence    -> scale when portfolio allows

    EXIT leaves when the thesis is structurally wrong or the target is met.
    REDUCE cuts size when validated risk falls materially or evidence weakens.
    """
    ev = fire_decision.expected_net_value
    current = max(0.0, float(current_risk_usd))
    target = max(0.0, float(target_risk_usd))
    if current > 0 and (invalidated or target_reached or opposite_side):
        if invalidated:
            reason = "structural_invalidation"
        elif opposite_side:
            reason = "opposite_side_invalidates_open_thesis"
        else:
            reason = "structure_target_reached"
        return ThesisFireDecision("exit", reason, ev)
    fire_ok = fire_decision.action == "fire"
    if current <= 0:
        if fire_ok:
            return ThesisFireDecision("fire", fire_decision.reason, ev)
        return ThesisFireDecision("skip", fire_decision.reason, ev)
    # OPEN thesis below here. Entry-gate failures must NOT close it.
    if not fire_ok:
        reason = str(fire_decision.reason or "")
        base_reason = reason.split(":", 1)[0]
        if base_reason in ENTRY_GATE_REASONS or reason.startswith("sizing:") \
                or reason.startswith("trade_economics:"):
            return ThesisFireDecision("hold", f"open_thesis_holds:{reason}", ev)
        if reason in EDGE_GONE_REASONS or reason.startswith("destructive_payoff"):
            # Material deterioration de-risks; the protective stop still owns
            # catastrophe. Full exit remains for structural invalidation.
            return ThesisFireDecision("reduce", f"edge_deteriorating:{reason}", ev)
        if target + 1e-12 < current:
            return ThesisFireDecision("reduce", reason or "weaker_target_exposure", ev)
        return ThesisFireDecision("hold", f"open_thesis_holds:{reason}", ev)
    if last_information_id and str(information_id) == str(last_information_id):
        return ThesisFireDecision("skip", "redundant_information", ev)
    if target > current + 1e-12:
        return ThesisFireDecision("scale", "new_evidence_increase_exposure", ev)
    if target + 1e-12 < current:
        return ThesisFireDecision("reduce", "new_evidence_decrease_exposure", ev)
    return ThesisFireDecision("skip", "hold_at_target_exposure", ev)
