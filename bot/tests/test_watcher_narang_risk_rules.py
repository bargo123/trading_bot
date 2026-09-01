from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


def _regime(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_relationship_current": 1.20,
        "narang_relationship_baseline": 1.00,
        "narang_relationship_shift_limit": 0.30,
        "narang_regime_data_provenance": "observed rolling relationship metrics",
    }
    state.update(overrides)
    return state


def _shock(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_observed_move": 0.010,
        "narang_model_expected_move": 0.008,
        "narang_unexplained_move_limit": 0.005,
        "narang_external_event_flag": False,
        "narang_shock_data_provenance": "observed timestamped market and event state",
    }
    state.update(overrides)
    return state


def _contagion(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "narang_strategy_overlap_score": 0.20,
        "narang_strategy_overlap_limit": 0.50,
        "narang_common_investor_exposure": 0.30,
        "narang_common_investor_limit": 0.60,
        "narang_contagion_data_provenance": "observed portfolio overlap and exposure",
    }
    state.update(overrides)
    return state


def test_narang_regime_warning_flags_a_large_relationship_shift():
    clear = evaluate_module("narang_regime_change_warning", _regime())
    assert clear["narang_regime_action"] == "REGIME_WITHIN_BASELINE"

    alert = evaluate_module(
        "narang_regime_change_warning",
        _regime(narang_relationship_current=1.40),
    )
    assert alert["narang_regime_action"] == "REGIME_CHANGE_ALERT"
    assert alert["view"] == "WAIT"


def test_narang_exogenous_shock_filter_abstains_on_event_or_unexplained_move():
    clear = evaluate_module("narang_exogenous_shock_filter", _shock())
    assert clear["narang_shock_action"] == "SHOCK_CLEAR"

    event = evaluate_module(
        "narang_exogenous_shock_filter",
        _shock(narang_external_event_flag=True),
    )
    assert event["narang_shock_action"] == "SHOCK_ABSTAIN"

    unexplained = evaluate_module(
        "narang_exogenous_shock_filter",
        _shock(narang_observed_move=0.020),
    )
    assert unexplained["narang_shock_action"] == "SHOCK_ABSTAIN"


def test_narang_contagion_warning_checks_overlap_and_common_exposure():
    clear = evaluate_module("narang_contagion_exposure", _contagion())
    assert clear["narang_contagion_action"] == "CONTAGION_WITHIN_LIMITS"

    alert = evaluate_module(
        "narang_contagion_exposure",
        _contagion(narang_strategy_overlap_score=0.80),
    )
    assert alert["narang_contagion_action"] == "CONTAGION_ALERT"


def test_narang_risk_rules_require_observed_provenance():
    missing = evaluate_module(
        "narang_regime_change_warning",
        _regime(narang_regime_data_provenance="synthetic fixture"),
    )
    assert missing["view"] == "MISSING_DATA"
