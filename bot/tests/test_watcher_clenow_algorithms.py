from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


SOURCE = "Following the Trend — Diversified Managed Futures Trading"


def _state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "clenow_timeframe": "daily",
        "clenow_fast_ema": 1.105,
        "clenow_slow_ema": 1.100,
        "clenow_trend_filter": "up",
        "clenow_breakout_direction": "up",
        "clenow_breakout_confirmation": "confirmed",
        "clenow_atr": 0.002,
        "clenow_risk_factor": 0.002,
        "clenow_data_provenance": "causal_daily_quote_proxy",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("side", "trend", "breakout", "expected"),
    [("BUY", "up", "up", "BUY"), ("SELL", "down", "down", "SELL")],
)
def test_clenow_breakout_must_agree_with_dual_ema_trend_filter(side, trend, breakout, expected):
    result = evaluate_module(
        "clenow_dual_ema_breakout",
        _state(
            side=side,
            clenow_trend_filter=trend,
            clenow_breakout_direction=breakout,
            clenow_fast_ema=1.105 if trend == "up" else 1.095,
            clenow_slow_ema=1.100 if trend == "up" else 1.100,
        ),
    )

    assert result["view"] == expected
    assert result["applicability"] == "APPLICABLE"
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"clenow_breakout_confirmation": "not_confirmed"},
        {"clenow_trend_filter": "range"},
        {"clenow_breakout_direction": "down"},
        {"clenow_atr": 0.0},
        {"clenow_timeframe": "intraday"},
    ],
)
def test_clenow_waits_when_trend_breakout_or_volatility_risk_evidence_is_invalid(overrides):
    result = evaluate_module("clenow_dual_ema_breakout", _state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_clenow_fails_closed_without_causal_evidence():
    result = evaluate_module("clenow_dual_ema_breakout", {"symbol": "EURUSD", "side": "BUY"})

    assert result["view"] == "MISSING_DATA"
    assert result["missing_inputs"]
    assert result["execution_authority"] is False


def _countertrend_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "clenow_countertrend_fast_ema40": 1.1050,
        "clenow_countertrend_slow_ema80": 1.1000,
        "clenow_countertrend_recent_high_20": 1.1100,
        "clenow_countertrend_current_price": 1.1040,
        "clenow_countertrend_atr": 0.0020,
        "clenow_countertrend_data_provenance": "observed_timestamped_daily_countertrend_inputs",
    }
    state.update(overrides)
    return state


def test_clenow_countertrend_buys_only_a_volatility_scaled_dip_in_a_bull_market():
    result = evaluate_module("clenow_countertrend_pullback", _countertrend_state())

    assert result["view"] == "BUY"
    assert result["clenow_pullback_atr_multiple"] == pytest.approx(3.0)
    assert result["clenow_countertrend_entry"] is True
    assert result["source_books"] == [SOURCE]
    assert result["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"side": "SELL"},
        {"clenow_countertrend_fast_ema40": 1.0950},
        {"clenow_countertrend_current_price": 1.1050},
        {"clenow_countertrend_atr": 0.0},
    ],
)
def test_clenow_countertrend_waits_without_the_source_bull_market_dip(overrides):
    result = evaluate_module("clenow_countertrend_pullback", _countertrend_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def _carry_state(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "clenow_curve_state": "contango",
        "clenow_steepest_annualized_carry": -0.18,
        "clenow_carry_liquidity_sufficient": True,
        "clenow_weekly_rebalance": True,
        "clenow_carry_data_provenance": "observed_timestamped_futures_curve",
    }
    state.update(overrides)
    return state


def test_clenow_term_structure_carry_requires_a_liquid_weekly_extreme():
    contango = evaluate_module("clenow_term_structure_carry", _carry_state())
    backwardation = evaluate_module(
        "clenow_term_structure_carry",
        _carry_state(
            side="BUY",
            clenow_curve_state="backwardation",
            clenow_steepest_annualized_carry=0.08,
        ),
    )

    assert contango["view"] == "SELL"
    assert backwardation["view"] == "BUY"
    assert contango["clenow_carry_threshold"] == pytest.approx(0.15)
    assert contango["execution_authority"] is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"clenow_steepest_annualized_carry": -0.10},
        {"clenow_carry_liquidity_sufficient": False},
        {"clenow_weekly_rebalance": False},
        {"clenow_curve_state": "flat"},
    ],
)
def test_clenow_term_structure_waits_when_carry_is_not_tradeable(overrides):
    result = evaluate_module("clenow_term_structure_carry", _carry_state(**overrides))

    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_clenow_core_model_requires_a_new_100_day_extreme_in_ema_trend():
    result = evaluate_module(
        "clenow_core_breakout",
        _state(
            clenow_core_timeframe="daily",
            clenow_core_fast_ema=1.105,
            clenow_core_slow_ema=1.100,
            clenow_core_trend="up",
            clenow_core_extreme_type="new_100_day_high",
            clenow_core_breakout_confirmed=True,
            clenow_core_data_provenance="observed timestamped daily breakout study",
        ),
    )

    assert result["view"] == "BUY"
    assert result["clenow_core_assessment"] == "BUY_100_DAY_HIGH"
    assert result["execution_authority"] is False


def test_clenow_core_exit_reports_the_source_50_day_exit_trigger():
    result = evaluate_module(
        "clenow_core_exit",
        _state(
            clenow_exit_trigger="50_day_low",
            clenow_exit_trend_state="bullish",
            clenow_exit_data_provenance="observed timestamped daily exit study",
        ),
    )

    assert result["clenow_exit_action"] == "EXIT_LONG"
    assert result["directional_claim"] is False


def test_clenow_volatility_trailing_stop_only_tightens_for_a_long():
    result = evaluate_module(
        "clenow_volatility_trailing_stop",
        _state(
            side="BUY",
            clenow_trailing_extreme_price=1.1100,
            clenow_trailing_current_price=1.1080,
            clenow_trailing_atr=0.0020,
            clenow_trailing_atr_multiple=3.0,
            clenow_previous_stop_price=1.1000,
            clenow_trailing_data_provenance="observed timestamped volatility stop study",
        ),
    )

    assert result["clenow_trailing_action"] == "MOVE_STOP_UP"
    assert result["clenow_proposed_stop_price"] == pytest.approx(1.1040)


def test_clenow_style_diversification_validates_monthly_three_style_weights():
    result = evaluate_module(
        "clenow_style_diversification",
        _state(
            clenow_style_weights={"trend_following": 0.34, "counter_trend": 0.33, "curve_trading": 0.33},
            clenow_style_rebalance_frequency="monthly",
            clenow_style_data_provenance="observed timestamped portfolio study",
        ),
    )

    assert result["clenow_style_assessment"] == "VALID_EQUAL_STYLE_BLEND"
    assert result["clenow_style_action"] == "REBALANCE_MONTHLY"
