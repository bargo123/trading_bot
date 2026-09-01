import pytest

from aegis.research.watcher_algorithms import evaluate_module


def test_deprado_sample_uniqueness_is_the_average_inverse_concurrency():
    result = evaluate_module(
        "deprado_sample_uniqueness",
        {
            "deprado_concurrency_counts": [1, 2, 4, 4],
            "deprado_uniqueness_data_provenance": "observed_label_concurrency",
        },
    )

    assert result["view"] == "WAIT"
    assert result["deprado_average_uniqueness"] == pytest.approx(0.5)
    assert result["deprado_uniqueness_assessment"] == "UNIQUENESS_MEASURED"
    assert result["execution_authority"] is False


def test_deprado_sequential_bootstrap_weights_the_next_draw_by_incremental_uniqueness():
    result = evaluate_module(
        "deprado_sequential_bootstrap",
        {
            "deprado_indicator_matrix": [
                [1, 1, 0],
                [1, 0, 1],
                [0, 1, 1],
            ],
            "deprado_selected_indices": [0],
            "deprado_sequential_bootstrap_data_provenance": "observed_label_indicator_matrix",
        },
    )

    probabilities = result["deprado_next_draw_probabilities"]
    assert probabilities[0] < probabilities[1]
    assert probabilities[0] < probabilities[2]
    assert sum(probabilities) == pytest.approx(1.0)
    assert result["deprado_sequential_bootstrap_assessment"] == "UNIQUENESS_WEIGHTED_DRAW"


def test_deprado_cpcv_builds_chronological_combinations_with_group_purge_and_embargo():
    result = evaluate_module(
        "deprado_combinatorial_purged_cv",
        {
            "deprado_group_count": 5,
            "deprado_test_group_count": 2,
            "deprado_purge_group_count": 1,
            "deprado_embargo_group_count": 1,
            "deprado_cpcv_data_provenance": "observed_chronological_groups",
        },
    )

    assert result["deprado_cpcv_split_count"] == 10
    assert result["deprado_cpcv_splits"][0]["test_groups"] == [0, 1]
    assert result["deprado_cpcv_splits"][0]["train_groups"] == [4]
    assert result["deprado_cpcv_assessment"] == "PURGED_COMBINATORIAL_SPLITS"


def test_deprado_probabilistic_sharpe_adjusts_for_sample_size_and_non_normality():
    result = evaluate_module(
        "deprado_probabilistic_sharpe",
        {
            "deprado_excess_returns": [0.02, 0.01, 0.015, -0.002, 0.01, 0.012],
            "deprado_target_sharpe": 0.0,
            "deprado_returns_data_provenance": "observed_completed_net_returns",
        },
    )

    assert 0.0 < result["deprado_probabilistic_sharpe"] <= 1.0
    assert result["deprado_observed_sharpe"] > 0
    assert result["deprado_probabilistic_sharpe"] > 0.5
    assert result["deprado_psr_assessment"] == "PROBABILITY_SHARPE_ABOVE_TARGET"


def test_deprado_deflated_sharpe_accounts_for_the_number_of_trials():
    result = evaluate_module(
        "deprado_deflated_sharpe",
        {
            "deprado_selected_excess_returns": [0.02, 0.01, 0.015, -0.002, 0.01, 0.012],
            "deprado_trial_sharpes": [0.1, 0.2, 0.3, 0.4],
            "deprado_returns_data_provenance": "observed_completed_net_returns",
            "deprado_trial_data_provenance": "observed_recorded_trials",
        },
    )

    assert 0.0 <= result["deprado_deflated_sharpe"] <= 1.0
    assert result["deprado_expected_max_sharpe"] > 0
    assert result["deprado_dsr_assessment"] in {
        "SELECTION_ADJUSTED_SUPPORT",
        "SELECTION_ADJUSTED_NOT_SUPPORTED",
    }


def test_deprado_strategy_failure_probability_is_a_post_outcome_diagnostic():
    result = evaluate_module(
        "deprado_strategy_failure_probability",
        {
            "deprado_bet_returns": [0.02, 0.02, -0.01, 0.02, -0.01, -0.01],
            "deprado_stop_loss": -0.01,
            "deprado_profit_taking": 0.02,
            "deprado_target_sharpe": 1.0,
            "deprado_bets_per_year": 260,
            "deprado_assessment_years": 1,
            "deprado_bootstrap_iterations": 200,
            "deprado_bootstrap_seed": 7,
            "deprado_returns_data_provenance": "observed_completed_net_returns",
        },
    )

    assert 0.0 <= result["deprado_strategy_failure_probability"] <= 1.0
    assert 0.0 < result["deprado_precision_threshold"] < 1.0
    assert result["analysis_stage"] == "post_outcome_validation"
    assert result["deprado_strategy_failure_assessment"] in {
        "STRATEGY_FAILURE_RISK_ACCEPTABLE",
        "HIGH_STRATEGY_FAILURE_RISK",
    }
