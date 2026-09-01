from __future__ import annotations

from aegis.research.watcher_algorithms import evaluate_module


def test_elliott_wave_three_must_travel_beyond_wave_one():
    result = evaluate_module(
        "elliott_wave_three_extension",
        {
            "symbol": "EURUSD",
            "side": "BUY",
            "elliott_wave_direction": "up",
            "elliott_wave_3_beyond_wave_1": True,
            "elliott_wave_structure_confirmed": True,
            "elliott_data_provenance": "observed_wave_annotation",
        },
    )
    assert result["view"] == "BUY"
    assert result["elliott_wave_three_assessment"] == "WAVE_3_BEYOND_WAVE_1"

    invalid = dict(
        symbol="EURUSD",
        side="BUY",
        elliott_wave_direction="up",
        elliott_wave_3_beyond_wave_1=False,
        elliott_wave_structure_confirmed=True,
        elliott_data_provenance="observed_wave_annotation",
    )
    assert evaluate_module("elliott_wave_three_extension", invalid)["view"] == "WAIT"


def test_elliott_diagonal_keeps_the_motive_direction_and_third_wave_rule():
    result = evaluate_module(
        "elliott_diagonal_rules",
        {
            "symbol": "EURUSD",
            "side": "SELL",
            "elliott_diagonal_type": "ending",
            "elliott_diagonal_direction": "down",
            "elliott_diagonal_wave_3_not_shortest": True,
            "elliott_diagonal_structure_confirmed": True,
            "elliott_data_provenance": "observed_wave_annotation",
        },
    )
    assert result["view"] == "SELL"
    assert result["elliott_diagonal_assessment"] == "VALID_ENDING_DIAGONAL"
