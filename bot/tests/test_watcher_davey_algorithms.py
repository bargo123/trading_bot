import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _night_state(**overrides):
    state = {
        "side": "SELL",
        "davey_night_time_hhmm": 1900,
        "davey_night_position_flat": True,
        "davey_night_nb": 3,
        "davey_night_natr": 5,
        "davey_night_atr_multiplier": 2.0,
        "davey_night_tr_multiplier": 0.5,
        "davey_night_stop_loss": 425.0,
        "davey_night_current_price": 1.1340,
        "davey_night_high_history": [1.1300, 1.1400, 1.1500],
        "davey_night_low_history": [1.1200, 1.1300, 1.1400],
        "davey_night_true_range_history": [0.001] * 5,
        "davey_night_data_provenance": "observed historical bar replay",
    }
    state.update(overrides)
    return state


def test_davey_euro_night_chooses_closest_limit_and_builds_bracket():
    result = evaluate_module("davey_euro_night_strategy", _night_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "SELL"
    assert result["davey_night_action"] == "PLACE_SHORT_LIMIT"
    assert result["davey_night_selected_side"] == "SELL"
    assert result["davey_night_entry_price"] == pytest.approx(1.1320)
    assert result["davey_night_target_price"] == pytest.approx(1.1315)
    assert result["davey_night_stop_loss"] == pytest.approx(425.0)
    assert result["execution_authority"] is False
    assert result["uses_future_data"] is False


def test_davey_euro_night_is_session_and_provenance_gated():
    outside = evaluate_module(
        "davey_euro_night_strategy", _night_state(davey_night_time_hhmm=1500)
    )
    missing_provenance = evaluate_module(
        "davey_euro_night_strategy",
        _night_state(davey_night_data_provenance="synthetic fixture"),
    )

    assert outside["davey_night_action"] == "OUTSIDE_NIGHT_SESSION"
    assert outside["view"] == "WAIT"
    assert missing_provenance["applicability"] == "MISSING_DATA"


def _day_state(**overrides):
    state = {
        "side": "SELL",
        "davey_day_time_hhmm": 1400,
        "davey_day_traded_this_session": False,
        "davey_day_xb": 3,
        "davey_day_xb2": 2,
        "davey_day_pip_add": 2.0,
        "davey_day_stop_loss": 425.0,
        "davey_day_profit_target": 5000.0,
        "davey_day_high_history": [1.1000, 1.1010, 1.1020, 1.1050],
        "davey_day_low_history": [1.0900, 1.0910, 1.0920, 1.0950],
        "davey_day_close_history": [1.1000, 1.1010, 1.1020, 1.0980],
        "davey_day_data_provenance": "observed historical bar replay",
    }
    state.update(overrides)
    return state


def test_davey_euro_day_reversal_uses_source_limit_offset_and_session_guard():
    result = evaluate_module("davey_euro_day_strategy", _day_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "SELL"
    assert result["davey_day_action"] == "PLACE_SHORT_LIMIT"
    assert result["davey_day_entry_price"] == pytest.approx(1.1052)
    assert result["davey_day_stop_loss"] == pytest.approx(425.0)
    assert result["davey_day_profit_target"] == pytest.approx(5000.0)
    assert result["execution_authority"] is False


def test_davey_euro_day_reversal_rejects_second_trade_and_missing_trigger():
    already_traded = evaluate_module(
        "davey_euro_day_strategy", _day_state(davey_day_traded_this_session=True)
    )
    no_trigger = evaluate_module(
        "davey_euro_day_strategy",
        _day_state(
            davey_day_close_history=[1.1000, 1.1010, 1.1020, 1.1010],
        ),
    )

    assert already_traded["davey_day_action"] == "SESSION_TRADE_ALREADY_USED"
    assert already_traded["view"] == "WAIT"
    assert no_trigger["davey_day_action"] == "NO_REVERSAL_TRIGGER"
    assert no_trigger["view"] == "WAIT"


def test_davey_three_bar_baseline_reversal_and_capped_atr_stop():
    result = evaluate_module(
        "davey_three_bar_baseline",
        {
            "side": "BUY",
            "davey_baseline_close_history": [1.1010, 1.1000, 1.0990],
            "davey_baseline_true_range_history": [0.002] * 14,
            "davey_baseline_atr_multiplier": 0.75,
            "davey_baseline_big_point_value": 10.0,
            "davey_baseline_stop_cap": 0.01,
            "davey_baseline_data_provenance": "observed historical bar replay",
        },
    )

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "BUY"
    assert result["davey_baseline_action"] == "BUY_NEXT_BAR"
    assert result["davey_baseline_atr14"] == pytest.approx(0.002)
    assert result["davey_baseline_stop_loss"] == pytest.approx(0.01)
    assert result["execution_authority"] is False


def test_davey_three_bar_baseline_fails_closed_without_three_ordered_closes():
    result = evaluate_module(
        "davey_three_bar_baseline",
        {
            "davey_baseline_close_history": [1.1000, 1.1000, 1.1000],
            "davey_baseline_true_range_history": [0.002] * 14,
            "davey_baseline_atr_multiplier": 0.75,
            "davey_baseline_big_point_value": 10.0,
            "davey_baseline_stop_cap": 0.01,
            "davey_baseline_data_provenance": "observed historical bar replay",
        },
    )

    assert result["davey_baseline_action"] == "NO_THREE_BAR_TRIGGER"
    assert result["view"] == "WAIT"
