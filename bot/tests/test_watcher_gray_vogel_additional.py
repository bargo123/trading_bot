from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Wesley R. Gray and Jack R. Vogel — Quantitative Momentum"


def _high_52(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_52w_price_ratio": 0.96,
        "gray_52w_long_cutoff": 0.90,
        "gray_52w_short_cutoff": 0.20,
        "gray_52w_reference_window": "previous 52 weeks",
        "gray_52w_holding_months": 3,
        "gray_52w_rebalance_frequency": "monthly",
        "gray_52w_data_provenance": "observed historical daily prices",
    }
    state.update(overrides)
    return state


def _absolute(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_absolute_momentum_return": 0.70,
        "gray_absolute_winner_cutoff": 0.60,
        "gray_absolute_loser_cutoff": -0.35,
        "gray_absolute_cutoff_sample_n": 2400,
        "gray_absolute_candidate_count": 5,
        "gray_absolute_portfolio_cap": 10,
        "gray_absolute_data_provenance": "observed expanding historical return distribution",
    }
    state.update(overrides)
    return state


def _stop(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_stop_loss_position_return": -0.06,
        "gray_stop_loss_threshold": 0.05,
        "gray_stop_loss_monitoring_frequency": "daily",
        "gray_stop_loss_rebalance_state": "monthly",
        "gray_stop_loss_data_provenance": "observed historical position returns",
    }
    state.update(overrides)
    return state


def _overlay(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_overlay_current_price": 110.0,
        "gray_overlay_sma": 100.0,
        "gray_overlay_market_return": 0.12,
        "gray_overlay_risk_free_return": 0.03,
        "gray_overlay_lookback_months": 12,
        "gray_overlay_data_provenance": "observed historical index prices",
    }
    state.update(overrides)
    return state


def _fundamental(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "gray_fundamental_signal": "SUE",
        "gray_fundamental_score": 0.95,
        "gray_fundamental_long_cutoff": 0.90,
        "gray_fundamental_short_cutoff": 0.10,
        "gray_fundamental_sample_n": 240,
        "gray_fundamental_volatility_scale": 1.0,
        "gray_fundamental_data_provenance": "observed timestamped earnings-surprise history",
    }
    state.update(overrides)
    return state


def _rebalance(**overrides):
    state = {
        "gray_rebalance_portfolio_size": 50,
        "gray_rebalance_universe_size": 500,
        "gray_rebalance_holding_months": 1,
        "gray_rebalance_frequency_months": 1,
        "gray_rebalance_expected_gross_edge": 0.15,
        "gray_rebalance_cost_per_rebalance": 0.005,
        "gray_rebalance_concentration_cutoff": 0.20,
        "gray_rebalance_overlapping_portfolios": False,
        "gray_rebalance_data_provenance": "observed historical portfolio study",
    }
    state.update(overrides)
    return state


def test_gray_vogel_52_week_high_exposes_signal_and_monthly_robustness_warning():
    result = evaluate_module("gray_vogel_52_week_high", _high_52())
    assert result["view"] == "BUY"
    assert result["gray_52w_assessment"] == "NEAR_52_WEEK_HIGH_HYPOTHESIS"
    assert result["gray_52w_evidence_status"] == "HYPOTHESIS_ONLY"
    assert result["source_books"] == [SOURCE]

    fragile = evaluate_module(
        "gray_vogel_52_week_high",
        _high_52(gray_52w_holding_months=1),
    )
    assert fragile["view"] == "WAIT"
    assert fragile["gray_52w_assessment"] == "MONTHLY_ROBUSTNESS_WARNING"


def test_gray_vogel_absolute_strength_requires_capacity_and_dynamic_cutoffs():
    result = evaluate_module("gray_vogel_absolute_strength", _absolute())
    assert result["view"] == "BUY"
    assert result["gray_absolute_assessment"] == "ABSOLUTE_WINNER"

    too_large = evaluate_module(
        "gray_vogel_absolute_strength",
        _absolute(gray_absolute_candidate_count=11),
    )
    assert too_large["view"] == "WAIT"
    assert too_large["gray_absolute_assessment"] == "PORTFOLIO_CAPACITY_WARNING"

    no_signal = evaluate_module(
        "gray_vogel_absolute_strength",
        _absolute(gray_absolute_momentum_return=0.10),
    )
    assert no_signal["gray_absolute_assessment"] == "NO_ABSOLUTE_SIGNAL"


def test_gray_vogel_stop_loss_is_a_risk_observation_not_a_new_entry_signal():
    result = evaluate_module("gray_vogel_momentum_stop_loss", _stop())
    assert result["view"] == "WAIT"
    assert result["gray_stop_loss_action"] == "STOP_LOSS_TRIGGERED"
    assert result["directional_claim"] is False
    sell = evaluate_module(
        "gray_vogel_momentum_stop_loss",
        _stop(side="SELL", gray_stop_loss_position_return=0.06),
    )
    assert sell["gray_stop_loss_action"] == "STOP_LOSS_TRIGGERED"


def test_gray_vogel_time_series_overlay_separates_risk_on_from_defensive_state():
    risk_on = evaluate_module("gray_vogel_time_series_overlay", _overlay())
    assert risk_on["view"] == "WAIT"
    assert risk_on["gray_overlay_action"] == "RISK_ON_OVERLAY"
    assert risk_on["directional_claim"] is False

    defensive = evaluate_module(
        "gray_vogel_time_series_overlay",
        _overlay(gray_overlay_current_price=95.0),
    )
    assert defensive["gray_overlay_action"] == "DEFENSIVE_OVERLAY"


def test_gray_vogel_fundamental_momentum_keeps_earnings_signal_distinct():
    result = evaluate_module("gray_vogel_fundamental_momentum", _fundamental())
    assert result["view"] == "BUY"
    assert result["gray_fundamental_assessment"] == "FUNDAMENTAL_MOMENTUM_WINNER"
    assert result["gray_fundamental_signal"] == "SUE"

    loser = evaluate_module(
        "gray_vogel_fundamental_momentum",
        _fundamental(
            side="SELL",
            gray_fundamental_score=0.05,
        ),
    )
    assert loser["view"] == "SELL"
    assert loser["gray_fundamental_assessment"] == "FUNDAMENTAL_MOMENTUM_LOSER"


def test_gray_vogel_rebalance_tradeoff_requires_cost_positive_concentration_and_frequency_context():
    result = evaluate_module("gray_vogel_rebalance_tradeoff", _rebalance())
    assert result["view"] == "WAIT"
    assert result["gray_rebalance_assessment"] == "CONCENTRATED_FREQUENT_REBALANCE"
    assert result["gray_rebalance_net_edge"] == pytest.approx(0.145)
    assert result["directional_claim"] is False

    cost_dominated = evaluate_module(
        "gray_vogel_rebalance_tradeoff",
        _rebalance(gray_rebalance_expected_gross_edge=0.002),
    )
    assert cost_dominated["gray_rebalance_assessment"] == "COST_DOMINATES"

    overlap_required = evaluate_module(
        "gray_vogel_rebalance_tradeoff",
        _rebalance(
            gray_rebalance_holding_months=3,
            gray_rebalance_frequency_months=1,
            gray_rebalance_overlapping_portfolios=False,
        ),
    )
    assert overlap_required["gray_rebalance_assessment"] == "OVERLAP_REQUIRED"


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "gray_vogel_52_week_high",
        "gray_vogel_absolute_strength",
        "gray_vogel_momentum_stop_loss",
        "gray_vogel_time_series_overlay",
        "gray_vogel_fundamental_momentum",
    ],
)
def test_gray_vogel_additional_algorithms_fail_closed_without_observed_inputs(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False
