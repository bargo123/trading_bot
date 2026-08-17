"""Two-level firehose intelligence: promote the strategy, then gate each thesis."""
from __future__ import annotations

from aegis.intel.strategy_model import ValidatedStrategyModel, strategy_model_ready
from aegis.intel.thesis_fire import evaluate_thesis_action, evaluate_thesis_fire


def _promoted_model(**overrides) -> ValidatedStrategyModel:
    payload = dict(
        strategy_id="failed_break_v1",
        promoted=True,
        n_trades=80,
        n_losses=12,
        expectancy=0.04,
        profit_factor=1.4,
        bootstrap_p05=0.01,
        wins_erased_by_average_loss=0.5,
        wins_erased_by_tail_loss=1.2,
        validated_risk_fraction=0.10,
        artifact_hash="abc123",
    )
    payload.update(overrides)
    return ValidatedStrategyModel(**payload)


def test_unpromoted_strategy_blocks_even_beautiful_local_analogues():
    decision = evaluate_thesis_fire(
        strategy=None,
        state_expected_net_value=0.05,
        analogue_n=400,
        analogue_n_losses=40,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    assert decision.action == "skip"
    assert decision.reason == "no_validated_strategy_model"


def test_promoted_strategy_still_requires_positive_state_ev():
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=-0.01,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    assert decision.action == "skip"
    assert decision.reason == "state_ev_not_positive"


def test_promoted_strategy_still_requires_enough_state_analogues():
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=0.04,
        analogue_n=8,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    assert decision.action == "skip"
    assert decision.reason == "insufficient_analogue_evidence"


def test_promoted_strategy_does_not_require_this_thesis_to_have_five_losses():
    """Loss-tail sampling is a strategy-promotion gate, not a per-thesis quota."""
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=0.04,
        analogue_n=40,
        analogue_n_losses=1,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    assert decision.action == "fire"
    assert decision.reason == "positive_state_ev_on_validated_strategy"


def test_promoted_strategy_still_requires_calibrated_uncertainty():
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=0.04,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="insufficient_sample",
        eligible=False,
        portfolio_ok=True,
    )
    assert decision.action == "skip"
    assert decision.reason == "unacceptable_uncertainty"


def test_promoted_strategy_still_requires_portfolio_room():
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=0.04,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=False,
        portfolio_reason="currency_factor:JPY:long",
    )
    assert decision.action == "skip"
    assert "currency_factor" in decision.reason


def test_ready_thesis_fires_immediately_when_all_gates_pass():
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=0.04,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    assert decision.action == "fire"
    assert decision.reason == "positive_state_ev_on_validated_strategy"
    assert decision.expected_net_value == 0.04


def test_strategy_model_ready_requires_losses_and_sample_for_tail_risk():
    thin = _promoted_model(n_trades=80, n_losses=2, promoted=True)
    ok, reason = strategy_model_ready(thin)
    assert ok is False
    assert "loss" in reason

    short = _promoted_model(n_trades=12, n_losses=12, promoted=True)
    ok, reason = strategy_model_ready(short)
    assert ok is False
    assert "sample" in reason or "trades" in reason

    cosmetic = _promoted_model(wins_erased_by_average_loss=30.0, promoted=True)
    ok, reason = strategy_model_ready(cosmetic)
    assert ok is False
    assert "payoff" in reason or "wins_erased" in reason

    ready = _promoted_model()
    ok, reason = strategy_model_ready(ready)
    assert ok is True
    assert reason == "ok"


def test_evaluate_thesis_fire_refuses_unready_promoted_flag():
    """A JSON artifact with promoted=true is not enough if tail-risk fields fail."""
    decision = evaluate_thesis_fire(
        strategy=_promoted_model(n_losses=1, n_trades=80),
        state_expected_net_value=0.04,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    assert decision.action == "skip"
    assert "loss" in decision.reason


def test_payoff_metrics_feed_strategy_readiness():
    from aegis.intel.expected_value import payoff_metrics

    stats = payoff_metrics([0.20] * 60 + [-0.10] * 40)
    model = _promoted_model(
        n_trades=stats["n"],
        n_losses=stats["n_losses"],
        expectancy=stats["expectancy"],
        profit_factor=stats["profit_factor"],
        wins_erased_by_average_loss=stats["wins_erased_by_average_loss"],
        wins_erased_by_tail_loss=stats["wins_erased_by_tail_loss"],
    )
    ok, reason = strategy_model_ready(model)
    assert ok is True
    assert reason == "ok"


def _fire():
    return evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=0.04,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )


def test_flat_ready_thesis_fires():
    decision = evaluate_thesis_action(
        fire_decision=_fire(),
        information_id="info-a",
        last_information_id=None,
        current_risk_usd=0.0,
        target_risk_usd=1.0,
        invalidated=False,
    )
    assert decision.action == "fire"


def test_same_information_id_does_not_scale():
    decision = evaluate_thesis_action(
        fire_decision=_fire(),
        information_id="info-a",
        last_information_id="info-a",
        current_risk_usd=1.0,
        target_risk_usd=2.0,
        invalidated=False,
    )
    assert decision.action == "skip"
    assert decision.reason == "redundant_information"


def test_new_information_id_scales_when_target_rises():
    decision = evaluate_thesis_action(
        fire_decision=_fire(),
        information_id="info-b",
        last_information_id="info-a",
        current_risk_usd=1.0,
        target_risk_usd=2.0,
        invalidated=False,
    )
    assert decision.action == "scale"
    assert decision.reason == "new_evidence_increase_exposure"


def test_weaker_target_reduces():
    decision = evaluate_thesis_action(
        fire_decision=_fire(),
        information_id="info-b",
        last_information_id="info-a",
        current_risk_usd=2.0,
        target_risk_usd=0.5,
        invalidated=False,
    )
    assert decision.action == "reduce"


def test_invalidation_exits_open_thesis():
    decision = evaluate_thesis_action(
        fire_decision=_fire(),
        information_id="info-a",
        last_information_id="info-a",
        current_risk_usd=1.0,
        target_risk_usd=1.0,
        invalidated=True,
    )
    assert decision.action == "exit"
    assert decision.reason == "structural_invalidation"


def test_lost_edge_exits_open_thesis():
    skip = evaluate_thesis_fire(
        strategy=_promoted_model(),
        state_expected_net_value=-0.02,
        analogue_n=40,
        analogue_n_losses=8,
        uncertainty="calibrated",
        eligible=True,
        portfolio_ok=True,
    )
    decision = evaluate_thesis_action(
        fire_decision=skip,
        information_id="info-a",
        last_information_id="info-a",
        current_risk_usd=1.0,
        target_risk_usd=1.0,
        invalidated=False,
    )
    assert decision.action == "exit"
    assert decision.reason.startswith("edge_gone:")
