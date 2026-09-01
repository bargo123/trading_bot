import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _dislocation(prefix, **overrides):
    state = {
        "symbol": "EURUSD",
        f"{prefix}_residual": -2.5,
        f"{prefix}_threshold": 2.0,
        f"{prefix}_net_edge_after_cost": 0.001,
        f"{prefix}_direction": "BUY",
        f"{prefix}_quotes_synchronized": True,
        f"{prefix}_data_provenance": "observed_synchronized_quotes",
    }
    state.update(overrides)
    return state


@pytest.mark.parametrize(
    ("algorithm_id", "prefix"),
    [
        ("aldridge_triangular_arbitrage", "aldridge_triangle"),
        ("aldridge_index_composition_arbitrage", "aldridge_index"),
        ("aldridge_futures_basis_arbitrage", "aldridge_basis"),
        ("aldridge_futures_etf_arbitrage", "aldridge_futures_etf"),
    ],
)
def test_aldridge_cross_asset_arbitrage_requires_synchronization_and_positive_net_edge(algorithm_id, prefix):
    result = evaluate_module(algorithm_id, _dislocation(prefix))
    assert result["view"] == "BUY"
    assert result["execution_authority"] is False

    no_edge = evaluate_module(algorithm_id, _dislocation(prefix, **{f"{prefix}_net_edge_after_cost": -0.001}))
    assert no_edge["view"] == "WAIT"
    assert no_edge["reasons"]


def test_aldridge_uip_arbitrage_requires_aligned_rates_and_direction():
    result = evaluate_module(
        "aldridge_uip_arbitrage",
        {
            "aldridge_uip_residual": -2.2,
            "aldridge_uip_threshold": 2.0,
            "aldridge_uip_net_edge_after_cost": 0.002,
            "aldridge_uip_direction": "BUY",
            "aldridge_uip_rates_aligned": True,
            "aldridge_uip_data_provenance": "observed_timestamp_aligned_rates",
        },
    )
    assert result["view"] == "BUY"

    blocked = evaluate_module(
        "aldridge_uip_arbitrage",
        {
            "aldridge_uip_residual": -2.2,
            "aldridge_uip_threshold": 2.0,
            "aldridge_uip_net_edge_after_cost": 0.002,
            "aldridge_uip_direction": "BUY",
            "aldridge_uip_rates_aligned": False,
            "aldridge_uip_data_provenance": "observed_timestamp_aligned_rates",
        },
    )
    assert blocked["view"] == "WAIT"


def test_aldridge_volatility_curve_arbitrage_requires_validated_curve_relationship():
    result = evaluate_module(
        "aldridge_volatility_curve_arbitrage",
        {
            "aldridge_volatility_curve_residual": 2.4,
            "aldridge_volatility_curve_threshold": 2.0,
            "aldridge_volatility_curve_net_edge_after_cost": 0.003,
            "aldridge_volatility_curve_direction": "SELL",
            "aldridge_volatility_curve_stationarity": "validated",
            "aldridge_volatility_curve_data_provenance": "observed_option_curve",
        },
    )
    assert result["view"] == "SELL"

    invalid = evaluate_module(
        "aldridge_volatility_curve_arbitrage",
        {
            "aldridge_volatility_curve_residual": 2.4,
            "aldridge_volatility_curve_threshold": 2.0,
            "aldridge_volatility_curve_net_edge_after_cost": 0.003,
            "aldridge_volatility_curve_direction": "SELL",
            "aldridge_volatility_curve_stationarity": "not validated",
            "aldridge_volatility_curve_data_provenance": "observed_option_curve",
        },
    )
    assert invalid["view"] == "WAIT"


def test_aldridge_dual_class_arbitrage_requires_liquidity_and_edge():
    result = evaluate_module(
        "aldridge_dual_class_arbitrage",
        {
            "aldridge_dual_class_premium": 2.2,
            "aldridge_dual_class_threshold": 2.0,
            "aldridge_dual_class_net_edge_after_cost": 0.001,
            "aldridge_dual_class_direction": "SELL",
            "aldridge_dual_class_liquidity_ratio": 0.8,
            "aldridge_dual_class_data_provenance": "observed_same_issuer_quotes",
        },
    )
    assert result["view"] == "SELL"


def test_aldridge_risk_arbitrage_uses_probability_payoff_and_cost_once():
    result = evaluate_module(
        "aldridge_risk_arbitrage",
        {
            "aldridge_risk_arbitrage_probability": 0.8,
            "aldridge_risk_arbitrage_profit_if_success": 0.01,
            "aldridge_risk_arbitrage_loss_if_failure": 0.02,
            "aldridge_risk_arbitrage_cost_per_trade": 0.001,
            "aldridge_risk_arbitrage_direction": "BUY",
            "aldridge_risk_arbitrage_data_provenance": "observed_event_payoff_history",
        },
    )
    assert result["view"] == "BUY"
    assert result["aldridge_risk_arbitrage_expected_net_edge"] == pytest.approx(0.003)

    negative = evaluate_module(
        "aldridge_risk_arbitrage",
        {
            "aldridge_risk_arbitrage_probability": 0.5,
            "aldridge_risk_arbitrage_profit_if_success": 0.01,
            "aldridge_risk_arbitrage_loss_if_failure": 0.02,
            "aldridge_risk_arbitrage_cost_per_trade": 0.001,
            "aldridge_risk_arbitrage_direction": "BUY",
            "aldridge_risk_arbitrage_data_provenance": "observed_event_payoff_history",
        },
    )
    assert negative["view"] == "WAIT"
