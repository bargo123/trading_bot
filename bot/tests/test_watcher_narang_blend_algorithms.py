import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _state(**overrides):
    state = {
        "side": "BUY",
        "narang_alpha_forecasts": [0.012, 0.004, -0.002],
        "narang_alpha_weights": [0.5, 0.3, 0.2],
        "narang_blend_threshold": 0.003,
        "narang_blend_model_status": "validated point-in-time linear blend",
        "narang_blend_data_provenance": "observed out-of-sample forecasts",
    }
    state.update(overrides)
    return state


def test_narang_linear_blend_combines_forecasts_before_directional_decision():
    buy = evaluate_module("narang_linear_alpha_blend", _state())
    sell = evaluate_module(
        "narang_linear_alpha_blend",
        _state(side="SELL", narang_alpha_forecasts=[-0.012, -0.004, 0.002]),
    )
    weak = evaluate_module(
        "narang_linear_alpha_blend",
        _state(narang_alpha_forecasts=[0.004, 0.002, -0.002]),
    )

    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["narang_composite_forecast"] == pytest.approx(0.0068)
    assert buy["narang_blend_action"] == "COMPOSITE_FORECAST_SUPPORTS"
    assert weak["view"] == "WAIT"
    assert weak["narang_blend_action"] == "COMPOSITE_BELOW_THRESHOLD"
    assert buy["execution_authority"] is False


def test_narang_linear_blend_fails_closed_for_bad_weights_or_unvalidated_model():
    bad_weights = evaluate_module(
        "narang_linear_alpha_blend",
        _state(narang_alpha_weights=[0.5]),
    )
    unvalidated = evaluate_module(
        "narang_linear_alpha_blend",
        _state(narang_blend_model_status="not validated"),
    )
    synthetic = evaluate_module(
        "narang_linear_alpha_blend",
        _state(narang_blend_data_provenance="synthetic fixture"),
    )

    assert bad_weights["narang_blend_action"] == "INVALID_BLEND_INPUT"
    assert unvalidated["narang_blend_action"] == "MODEL_NOT_VALIDATED"
    assert synthetic["applicability"] == "MISSING_DATA"


def test_narang_rotation_ranks_factors_by_recent_observed_performance():
    result = evaluate_module(
        "narang_alpha_rotation",
        {
            "narang_factor_recent_performance": {
                "trend": [0.004, 0.003, 0.005],
                "reversion": [0.001, -0.002, 0.0005],
                "event": [-0.001, 0.002, -0.0005],
            },
            "narang_rotation_data_provenance": "observed factor replay",
        },
    )

    assert result["applicability"] == "APPLICABLE"
    assert result["narang_rotation_action"] == "ROTATE_TO_RECENT_STRONGEST"
    assert result["narang_selected_factor"] == "trend"
    assert result["narang_factor_ranking"][0][0] == "trend"
    assert result["directional_claim"] is False
    assert result["execution_authority"] is False


def test_narang_run_frequency_tradeoff_selects_cost_adjusted_replay_peak():
    result = evaluate_module(
        "narang_run_frequency_tradeoff",
        {
            "narang_run_frequency_grid_s": [0.5, 1.0, 2.0],
            "narang_run_frequency_gross_returns": [0.012, 0.010, 0.007],
            "narang_run_frequency_transaction_costs": [0.006, 0.003, 0.001],
            "narang_run_frequency_noise_penalties": [0.002, 0.0005, 0.0002],
            "narang_run_frequency_data_provenance": "observed chronological replay",
        },
    )

    assert result["applicability"] == "APPLICABLE"
    assert result["narang_run_frequency_action"] == "PREFER_INTERMEDIATE_FREQUENCY"
    assert result["narang_selected_run_frequency_s"] == 1.0
    assert result["narang_run_frequency_net_returns"] == pytest.approx([0.004, 0.0065, 0.0058])
    assert result["directional_claim"] is False
    assert result["execution_authority"] is False


def test_narang_run_frequency_tradeoff_fails_closed_for_unobserved_or_misaligned_replay():
    missing_provenance = evaluate_module(
        "narang_run_frequency_tradeoff",
        {
            "narang_run_frequency_grid_s": [1.0, 2.0],
            "narang_run_frequency_gross_returns": [0.01, 0.009],
            "narang_run_frequency_transaction_costs": [0.002, 0.001],
            "narang_run_frequency_noise_penalties": [0.001, 0.001],
        },
    )
    malformed = evaluate_module(
        "narang_run_frequency_tradeoff",
        {
            "narang_run_frequency_grid_s": [1.0, 2.0],
            "narang_run_frequency_gross_returns": [0.01],
            "narang_run_frequency_transaction_costs": [0.002, 0.001],
            "narang_run_frequency_noise_penalties": [0.001, 0.001],
            "narang_run_frequency_data_provenance": "observed replay",
        },
    )

    assert missing_provenance["applicability"] == "MISSING_DATA"
    assert "narang_run_frequency_data_provenance" in missing_provenance["missing_inputs"]
    assert malformed["narang_run_frequency_action"] == "INVALID_FREQUENCY_REPLAY"
