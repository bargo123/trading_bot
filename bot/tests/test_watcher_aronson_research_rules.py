import pytest

from aegis.research.watcher_algorithms import evaluate_module


def test_aronson_objective_rule_requires_causal_definition_and_timing():
    result = evaluate_module(
        "aronson_objective_rule_definition",
        {
            "aronson_rule_inputs": ["close", "volume"],
            "aronson_rule_operators": ["moving_average", "greater_than"],
            "aronson_signal_timing": "close_to_next_executable_quote",
            "aronson_no_lookahead": True,
            "aronson_data_provenance": "observed_quote_history",
        },
    )
    assert result["view"] == "WAIT"
    assert result["aronson_objectivity_assessment"] == "OBJECTIVE_CAUSAL_RULE"
    assert result["execution_authority"] is False

    missing_timing = evaluate_module(
        "aronson_objective_rule_definition",
        {
            "aronson_rule_inputs": ["close"],
            "aronson_rule_operators": ["threshold"],
            "aronson_no_lookahead": True,
            "aronson_data_provenance": "observed_quote_history",
        },
    )
    assert missing_timing["view"] == "MISSING_DATA"


def test_aronson_reality_check_uses_the_family_null_distribution():
    result = evaluate_module(
        "aronson_reality_check",
        {
            "side": "BUY",
            "aronson_rule_direction": "BUY",
            "aronson_observed_net_return": 0.01,
            "aronson_null_net_returns": [0.0] * 19 + [0.002],
            "aronson_rule_universe_n": 6402,
            "aronson_significance_level": 0.05,
            "aronson_data_provenance": "observed_walk_forward_permutation",
        },
    )
    assert result["view"] == "BUY"
    assert result["aronson_reality_check_p_value"] == pytest.approx(1 / 21)
    assert result["aronson_reality_check_assessment"] == "FAMILYWISE_SUPPORT"

    weak = evaluate_module(
        "aronson_reality_check",
        {
            "side": "BUY",
            "aronson_rule_direction": "BUY",
            "aronson_observed_net_return": 0.01,
            "aronson_null_net_returns": [0.02] * 20,
            "aronson_rule_universe_n": 6402,
            "aronson_significance_level": 0.05,
            "aronson_data_provenance": "observed_walk_forward_permutation",
        },
    )
    assert weak["view"] == "WAIT"
    assert weak["aronson_reality_check_assessment"] == "FAMILYWISE_NOT_SUPPORTED"


def test_aronson_reality_check_rejects_unbounded_or_noncausal_evidence():
    result = evaluate_module(
        "aronson_reality_check",
        {
            "aronson_rule_direction": "BUY",
            "aronson_observed_net_return": 0.01,
            "aronson_null_net_returns": [0.0] * 20,
            "aronson_rule_universe_n": 0,
            "aronson_significance_level": 0.05,
            "aronson_data_provenance": "synthetic_permutation",
        },
    )
    assert result["view"] == "MISSING_DATA"
    assert "aronson_rule_universe_n" in result["missing_inputs"]
    assert "aronson_data_provenance" in result["missing_inputs"]


def test_aronson_practical_significance_requires_after_cost_economics():
    result = evaluate_module(
        "aronson_practical_significance",
        {
            "side": "SELL",
            "aronson_rule_direction": "SELL",
            "aronson_observed_net_expectancy": 0.003,
            "aronson_practical_edge_floor": 0.001,
            "aronson_costs_included": True,
            "aronson_data_provenance": "observed_net_replay",
        },
    )
    assert result["view"] == "SELL"
    assert result["aronson_practical_assessment"] == "PRACTICALLY_SIGNIFICANT"

    no_costs = evaluate_module(
        "aronson_practical_significance",
        {
            "side": "SELL",
            "aronson_rule_direction": "SELL",
            "aronson_observed_net_expectancy": 0.003,
            "aronson_practical_edge_floor": 0.001,
            "aronson_costs_included": False,
            "aronson_data_provenance": "observed_net_replay",
        },
    )
    assert no_costs["view"] == "WAIT"


def test_aronson_detrends_rule_returns_against_position_bias():
    result = evaluate_module(
        "aronson_detrended_rule_return",
        {
            "aronson_rule_returns": [0.03, -0.01, 0.02],
            "aronson_market_returns": [0.01, 0.01, 0.01],
            "aronson_position_series": [1, -1, 1],
            "aronson_data_provenance": "observed_timestamp_aligned_returns",
        },
    )
    assert result["view"] == "WAIT"
    assert result["aronson_market_mean_return"] == pytest.approx(0.01)
    assert result["aronson_raw_mean_return"] == pytest.approx(0.0133333333)
    assert result["aronson_detrended_mean_return"] == pytest.approx(0.01)
    assert result["directional_claim"] is False


@pytest.mark.parametrize(
    "algorithm_id",
    [
        "aronson_objective_rule_definition",
        "aronson_reality_check",
        "aronson_practical_significance",
        "aronson_detrended_rule_return",
    ],
)
def test_aronson_perspectives_are_research_only(algorithm_id):
    result = evaluate_module(algorithm_id, {})
    assert result["execution_authority"] is False
    assert result["research_only"] is True
    assert result["uses_future_data"] is False
