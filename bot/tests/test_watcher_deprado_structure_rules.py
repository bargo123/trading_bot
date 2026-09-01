import pytest

from aegis.research.watcher_algorithms import evaluate_module


def test_deprado_cusum_emits_reset_events_from_observed_changes_and_expectations():
    result = evaluate_module(
        "deprado_cusum_filter",
        {
            "deprado_cusum_changes": [0.0, 0.7, 0.7, -0.2, -0.8, -0.8],
            "deprado_cusum_expected_changes": [0.0] * 6,
            "deprado_cusum_threshold": 1.0,
            "deprado_cusum_data_provenance": "observed_quote_changes",
        },
    )

    assert [event["direction"] for event in result["deprado_cusum_events"]] == ["UP", "DOWN"]
    assert [event["index"] for event in result["deprado_cusum_events"]] == [2, 5]
    assert result["deprado_cusum_assessment"] == "CHANGE_EVENTS_MEASURED"
    assert result["execution_authority"] is False


def test_deprado_entropy_is_shannon_entropy_and_not_a_directional_probability():
    result = evaluate_module(
        "deprado_entropy",
        {
            "deprado_entropy_symbols": ["UP", "UP", "DOWN", "DOWN"],
            "deprado_entropy_data_provenance": "observed_tick_signs",
        },
    )

    assert result["deprado_shannon_entropy_bits"] == pytest.approx(1.0)
    assert result["deprado_entropy_unique_symbols"] == 2
    assert result["directional_claim"] is False
    assert result["deprado_entropy_assessment"] == "ENTROPY_MEASURED"


def test_deprado_tick_imbalance_bars_use_tick_rule_and_reset_after_events():
    result = evaluate_module(
        "deprado_tick_imbalance_bar",
        {
            "deprado_tick_prices": [100.0, 101.0, 102.0, 103.0, 102.0, 101.0, 100.0],
            "deprado_tick_expected_bar_size": 3,
            "deprado_tick_buy_probability": 0.75,
            "deprado_tick_imbalance_data_provenance": "observed_ticks",
        },
    )

    assert result["deprado_tick_expected_imbalance"] == pytest.approx(1.5)
    assert result["deprado_tick_bar_events"][0]["direction"] == "UP"
    assert result["deprado_tick_bar_events"][0]["end_index"] == 2
    assert result["deprado_tick_bar_events"][1]["direction"] == "DOWN"
    assert result["deprado_tick_imbalance_assessment"] == "TICK_IMBALANCE_EVENTS_MEASURED"


def test_deprado_volume_and_dollar_imbalance_bars_use_signed_activity():
    common = {
        "deprado_imbalance_prices": [100.0, 101.0, 102.0, 101.0, 100.0],
        "deprado_imbalance_expected_bar_size": 3,
        "deprado_imbalance_buy_probability": 0.75,
        "deprado_imbalance_buy_mean": 2.0,
        "deprado_imbalance_sell_mean": 1.0,
        "deprado_imbalance_data_provenance": "observed_tick_activity",
    }
    volume = evaluate_module(
        "deprado_volume_imbalance_bar",
        {**common, "deprado_volume_values": [2.0, 2.0, 2.0, 1.0, 1.0]},
    )
    dollar = evaluate_module(
        "deprado_dollar_imbalance_bar",
        {**common, "deprado_dollar_values": [20.0, 20.0, 20.0, 10.0, 10.0], "deprado_imbalance_buy_mean": 20.0, "deprado_imbalance_sell_mean": 10.0},
    )

    assert volume["deprado_volume_expected_imbalance"] == pytest.approx(3.75)
    assert volume["deprado_volume_imbalance_events"][0]["direction"] == "UP"
    assert dollar["deprado_dollar_expected_imbalance"] == pytest.approx(37.5)
    assert dollar["deprado_dollar_imbalance_events"][0]["direction"] == "UP"


def test_deprado_tick_runs_bar_counts_runs_without_offsetting_sides():
    result = evaluate_module(
        "deprado_tick_runs_bar",
        {
            "deprado_runs_prices": [100.0, 101.0, 102.0, 101.0, 100.0, 99.0],
            "deprado_runs_expected_bar_size": 3,
            "deprado_runs_buy_probability": 0.75,
            "deprado_runs_data_provenance": "observed_ticks",
        },
    )

    assert result["deprado_tick_runs_expected"] == pytest.approx(2.25)
    assert result["deprado_tick_runs_events"][0]["direction"] == "DOWN"
    assert result["deprado_tick_runs_events"][0]["end_index"] == 5


def test_deprado_volume_and_dollar_runs_bars_measure_one_sided_activity():
    common = {
        "deprado_runs_prices": [100.0, 101.0, 102.0, 101.0, 100.0, 99.0],
        "deprado_runs_expected_bar_size": 3,
        "deprado_runs_buy_probability": 0.75,
        "deprado_runs_buy_mean": 2.0,
        "deprado_runs_sell_mean": 2.0,
        "deprado_runs_data_provenance": "observed_tick_activity",
    }
    volume = evaluate_module(
        "deprado_volume_runs_bar",
        {**common, "deprado_volume_run_values": [2.0, 2.0, 1.0, 2.0, 2.0, 2.0]},
    )
    dollar = evaluate_module(
        "deprado_dollar_runs_bar",
        {**common, "deprado_dollar_run_values": [20.0, 20.0, 10.0, 20.0, 20.0, 20.0], "deprado_runs_buy_mean": 20.0, "deprado_runs_sell_mean": 20.0},
    )

    assert volume["deprado_volume_runs_expected"] == pytest.approx(4.5)
    assert volume["deprado_volume_runs_events"][0]["direction"] == "DOWN"
    assert dollar["deprado_dollar_runs_expected"] == pytest.approx(45.0)
    assert dollar["deprado_dollar_runs_events"][0]["direction"] == "DOWN"


def test_deprado_tick_bars_group_observed_ticks_without_time_resampling():
    result = evaluate_module(
        "deprado_tick_bar",
        {
            "deprado_standard_prices": [100.0, 101.0, 99.0, 100.0, 102.0],
            "deprado_tick_bar_size": 2,
            "deprado_standard_bar_data_provenance": "observed_ticks",
        },
    )

    assert result["deprado_standard_bar_count"] == 3
    assert result["deprado_standard_bars"][0] == {
        "start_index": 0,
        "end_index": 1,
        "open": 100.0,
        "close": 101.0,
        "high": 101.0,
        "low": 100.0,
        "activity": 2.0,
    }


def test_deprado_volume_and_dollar_bars_close_when_activity_threshold_is_reached():
    common = {
        "deprado_standard_prices": [100.0, 101.0, 99.0, 100.0],
        "deprado_standard_bar_size": 3,
        "deprado_standard_bar_data_provenance": "observed_tick_activity",
    }
    volume = evaluate_module(
        "deprado_volume_bar",
        {**common, "deprado_standard_volumes": [1.0, 2.0, 1.0, 2.0]},
    )
    dollar = evaluate_module(
        "deprado_dollar_bar",
        {**common, "deprado_standard_dollars": [10.0, 20.0, 10.0, 20.0], "deprado_standard_bar_size": 30},
    )

    assert [bar["end_index"] for bar in volume["deprado_standard_bars"]] == [1, 3]
    assert [bar["end_index"] for bar in dollar["deprado_standard_bars"]] == [1, 3]
