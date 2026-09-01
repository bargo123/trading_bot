import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _turn_state(**overrides):
    state = {
        "side": "BUY",
        "lien_turn_timeframe": "daily",
        "lien_turn_entry_time_ny": "17:00",
        "lien_turn_entry_price": 1.1000,
        "lien_turn_pip_size": 0.0001,
        "lien_turn_daily_bars": [
            {"open": 1.1100, "close": 1.1080},
            {"open": 1.1080, "close": 1.1060},
            {"open": 1.1060, "close": 1.1040},
            {"open": 1.1040, "close": 1.1020},
            {"open": 1.1020, "close": 1.1010},
            {"open": 1.1010, "close": 1.1005},
            {"open": 1.1005, "close": 1.1000},
        ],
        "lien_turn_data_provenance": "observed historical daily bars",
    }
    state.update(overrides)
    return state


def _two_day_state(**overrides):
    state = {
        "side": "BUY",
        "lien_two_day_entry_price": 1.1200,
        "lien_two_day_pip_size": 0.0001,
        "lien_two_day_high_history": [1.1250, 1.1230],
        "lien_two_day_low_history": [1.1150, 1.1100],
        "lien_two_day_data_provenance": "observed historical daily bars",
    }
    state.update(overrides)
    return state


def _management_state(**overrides):
    state = {
        "side": "BUY",
        "lien_mgmt_entry_price": 1.1000,
        "lien_mgmt_current_price": 1.1060,
        "lien_mgmt_pip_size": 0.0001,
        "lien_mgmt_initial_risk_pips": 60,
        "lien_mgmt_trailing_distance_pips": 60,
        "lien_mgmt_partial_closed": False,
        "lien_mgmt_breakeven_stop_active": False,
        "lien_mgmt_parabolic_sar": 1.1010,
        "lien_mgmt_data_provenance": "observed historical trade state",
    }
    state.update(overrides)
    return state


def test_lien_high_probability_turn_uses_seven_daily_candles_and_30_60_120_pip_plan():
    result = evaluate_module("lien_high_probability_turn", _turn_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "BUY"
    assert result["lien_turn_action"] == "BUY_EXTENSION_TURN"
    assert result["lien_turn_consecutive_days"] == 7
    assert result["lien_turn_stop_price"] == pytest.approx(1.0970)
    assert result["lien_turn_scale_out_price"] == pytest.approx(1.1060)
    assert result["lien_turn_final_target_price"] == pytest.approx(1.1120)
    assert result["lien_turn_scale_out_pips"] == 60
    assert result["lien_turn_final_target_pips"] == 120
    assert result["execution_authority"] is False


def test_lien_high_probability_turn_short_is_the_mirrored_source_rule():
    bars = [
        {"open": 1.1000, "close": 1.1020},
        {"open": 1.1020, "close": 1.1040},
        {"open": 1.1040, "close": 1.1060},
        {"open": 1.1060, "close": 1.1080},
        {"open": 1.1080, "close": 1.1100},
        {"open": 1.1100, "close": 1.1110},
        {"open": 1.1110, "close": 1.1120},
    ]
    result = evaluate_module(
        "lien_high_probability_turn",
        _turn_state(side="SELL", lien_turn_entry_price=1.1120, lien_turn_daily_bars=bars),
    )

    assert result["view"] == "SELL"
    assert result["lien_turn_action"] == "SELL_EXTENSION_TURN"
    assert result["lien_turn_stop_price"] == pytest.approx(1.1150)
    assert result["lien_turn_scale_out_price"] == pytest.approx(1.1060)
    assert result["lien_turn_final_target_price"] == pytest.approx(1.1000)


def test_lien_high_probability_turn_requires_observed_daily_state_and_entry_time():
    missing = evaluate_module(
        "lien_high_probability_turn",
        _turn_state(lien_turn_data_provenance="synthetic fixture"),
    )
    wrong_time = evaluate_module(
        "lien_high_probability_turn",
        _turn_state(lien_turn_entry_time_ny="16:59"),
    )
    short_run = evaluate_module(
        "lien_high_probability_turn",
        _turn_state(lien_turn_daily_bars=_turn_state()["lien_turn_daily_bars"][:6]),
    )

    assert missing["applicability"] == "MISSING_DATA"
    assert "lien_turn_data_provenance" in missing["missing_inputs"]
    assert wrong_time["lien_turn_action"] == "WAIT_FOR_1700_NEW_YORK_ENTRY"
    assert short_run["lien_turn_action"] == "INSUFFICIENT_DAILY_EXTENSION"


def test_lien_two_day_low_stop_places_ten_pips_below_two_day_low_for_long():
    result = evaluate_module("lien_two_day_low_stop", _two_day_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["lien_two_day_stop_action"] == "LONG_TWO_DAY_LOW_STOP"
    assert result["lien_two_day_reference_price"] == pytest.approx(1.1100)
    assert result["lien_two_day_stop_price"] == pytest.approx(1.1090)
    assert result["lien_two_day_offset_pips"] == 10
    assert result["execution_authority"] is False


def test_lien_two_day_low_stop_mirrors_the_stop_reference_for_short():
    result = evaluate_module(
        "lien_two_day_low_stop",
        _two_day_state(side="SELL", lien_two_day_entry_price=1.1080),
    )

    assert result["candidate_side"] == "SELL"
    assert result["lien_two_day_stop_action"] == "SHORT_TWO_DAY_HIGH_STOP"
    assert result["lien_two_day_reference_price"] == pytest.approx(1.1250)
    assert result["lien_two_day_stop_price"] == pytest.approx(1.1260)


def test_lien_two_day_low_stop_fails_closed_for_bad_geometry_or_provenance():
    bad_geometry = evaluate_module(
        "lien_two_day_low_stop",
        _two_day_state(lien_two_day_entry_price=1.1080),
    )
    missing_provenance = evaluate_module(
        "lien_two_day_low_stop",
        _two_day_state(lien_two_day_data_provenance="unavailable"),
    )

    assert bad_geometry["lien_two_day_stop_action"] == "INVALID_TWO_DAY_STOP_GEOMETRY"
    assert missing_provenance["applicability"] == "MISSING_DATA"
    assert "lien_two_day_data_provenance" in missing_provenance["missing_inputs"]


def test_lien_profit_management_scales_half_at_one_r_and_moves_stop_to_breakeven():
    result = evaluate_module("lien_two_stage_profit_management", _management_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["lien_mgmt_action"] == "SCALE_HALF_MOVE_TO_BREAKEVEN"
    assert result["lien_mgmt_current_profit_pips"] == pytest.approx(60)
    assert result["lien_mgmt_proposed_stop_price"] == pytest.approx(1.1000)
    assert result["lien_mgmt_trailing_stop_price"] == pytest.approx(1.1000)
    assert result["execution_authority"] is False


def test_lien_profit_management_trails_or_switches_to_parabolic_sar_after_scale_out():
    trailing = evaluate_module(
        "lien_two_stage_profit_management",
        _management_state(lien_mgmt_partial_closed=True, lien_mgmt_breakeven_stop_active=True, lien_mgmt_parabolic_sar=1.0990),
    )
    sar = evaluate_module(
        "lien_two_stage_profit_management",
        _management_state(lien_mgmt_partial_closed=True, lien_mgmt_breakeven_stop_active=True, lien_mgmt_parabolic_sar=1.1020),
    )

    assert trailing["lien_mgmt_action"] == "TRAIL_REMAINDER"
    assert trailing["lien_mgmt_proposed_stop_price"] == pytest.approx(1.1000)
    assert sar["lien_mgmt_action"] == "USE_PARABOLIC_SAR_STOP"
    assert sar["lien_mgmt_proposed_stop_price"] == pytest.approx(1.1020)


def test_lien_profit_management_holds_before_one_r_and_rejects_inconsistent_state():
    before_one_r = evaluate_module(
        "lien_two_stage_profit_management",
        _management_state(lien_mgmt_current_price=1.1030),
    )
    inconsistent = evaluate_module(
        "lien_two_stage_profit_management",
        _management_state(lien_mgmt_partial_closed=True, lien_mgmt_breakeven_stop_active=False),
    )

    assert before_one_r["lien_mgmt_action"] == "HOLD_INITIAL_STOP"
    assert before_one_r["lien_mgmt_proposed_stop_price"] == pytest.approx(1.0940)
    assert inconsistent["lien_mgmt_action"] == "INVALID_MANAGEMENT_STATE"
