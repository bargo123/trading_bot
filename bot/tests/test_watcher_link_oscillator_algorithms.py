import pytest

from aegis.research.watcher_algorithms import evaluate_module


def _stoch_state(**overrides):
    state = {
        "side": "BUY",
        "link_stoch_fast": 28.0,
        "link_stoch_slow": 24.0,
        "link_stoch_fast_previous": 22.0,
        "link_stoch_slow_previous": 20.0,
        "link_stoch_oversold": 20.0,
        "link_stoch_overbought": 80.0,
        "link_stoch_data_provenance": "observed historical oscillator values",
    }
    state.update(overrides)
    return state


def _rsi_state(**overrides):
    state = {
        "side": "BUY",
        "link_rsi_current": 52.0,
        "link_rsi_previous": 49.0,
        "link_rsi_fifty_line": 50.0,
        "link_rsi_stall_confirmed": False,
        "link_rsi_data_provenance": "observed historical oscillator values",
    }
    state.update(overrides)
    return state


def _macd_state(**overrides):
    state = {
        "side": "BUY",
        "link_macd_line": 0.004,
        "link_macd_signal_line": 0.002,
        "link_macd_data_provenance": "observed historical oscillator values",
    }
    state.update(overrides)
    return state


def test_link_stochastic_wave_entry_requires_both_lines_above_oversold_and_rising():
    result = evaluate_module("link_stochastic_wave_entry", _stoch_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "BUY"
    assert result["link_stoch_action"] == "BUY_BOTH_LINES_RISING_ABOVE_OVERSOLD"
    assert result["link_stoch_lines_above_oversold"] is True
    assert result["execution_authority"] is False


def test_link_stochastic_wave_entry_mirrors_the_rule_for_a_short_wave():
    result = evaluate_module(
        "link_stochastic_wave_entry",
        _stoch_state(
            side="SELL",
            link_stoch_fast=72.0,
            link_stoch_slow=76.0,
            link_stoch_fast_previous=78.0,
            link_stoch_slow_previous=80.0,
        ),
    )

    assert result["view"] == "SELL"
    assert result["link_stoch_action"] == "SELL_BOTH_LINES_FALLING_BELOW_OVERBOUGHT"
    assert result["link_stoch_lines_below_overbought"] is True


def test_link_stochastic_wave_entry_keeps_strong_extreme_trend_continuation_separate():
    buy = evaluate_module(
        "link_stochastic_wave_entry",
        _stoch_state(
            link_stoch_fast=88.0,
            link_stoch_slow=84.0,
            link_stoch_fast_previous=86.0,
            link_stoch_slow_previous=84.0,
        ),
    )
    sell = evaluate_module(
        "link_stochastic_wave_entry",
        _stoch_state(
            side="SELL",
            link_stoch_fast=12.0,
            link_stoch_slow=16.0,
            link_stoch_fast_previous=14.0,
            link_stoch_slow_previous=16.0,
        ),
    )

    assert buy["view"] == "BUY"
    assert buy["link_stoch_action"] == "BUY_OVERBOUGHT_TREND_CONTINUATION"
    assert sell["view"] == "SELL"
    assert sell["link_stoch_action"] == "SELL_OVERSOLD_TREND_CONTINUATION"


def test_link_stochastic_wave_entry_rejects_nonrising_or_unobserved_inputs():
    no_wave = evaluate_module(
        "link_stochastic_wave_entry",
        _stoch_state(link_stoch_fast_previous=30.0),
    )
    missing = evaluate_module(
        "link_stochastic_wave_entry",
        _stoch_state(link_stoch_data_provenance="synthetic fixture"),
    )

    assert no_wave["link_stoch_action"] == "NO_STOCHASTIC_WAVE"
    assert missing["applicability"] == "MISSING_DATA"
    assert "link_stoch_data_provenance" in missing["missing_inputs"]


def test_link_stochastic_cross_entry_requires_a_directional_line_cross_in_the_source_zone():
    buy = evaluate_module(
        "link_stochastic_cross_entry",
        _stoch_state(
            link_stoch_fast=32.0,
            link_stoch_slow=28.0,
            link_stoch_fast_previous=24.0,
            link_stoch_slow_previous=26.0,
            link_stoch_slow_bottomed=True,
        ),
    )
    sell = evaluate_module(
        "link_stochastic_cross_entry",
        _stoch_state(
            side="SELL",
            link_stoch_fast=68.0,
            link_stoch_slow=72.0,
            link_stoch_fast_previous=76.0,
            link_stoch_slow_previous=74.0,
            link_stoch_slow_bottomed=True,
        ),
    )
    wait = evaluate_module(
        "link_stochastic_cross_entry",
        _stoch_state(link_stoch_fast=25.0, link_stoch_slow=28.0),
    )

    assert buy["view"] == "BUY"
    assert buy["link_stoch_cross"] == "UP"
    assert buy["link_stoch_cross_strength"] == "STRONGER_AFTER_SLOW_BOTTOM"
    assert sell["view"] == "SELL"
    assert sell["link_stoch_cross"] == "DOWN"
    assert wait["link_stoch_action"] == "NO_STOCHASTIC_CROSS"


def test_link_stochastic_extreme_retest_requires_strength_pullback_and_retest_confirmation():
    buy = evaluate_module(
        "link_stochastic_extreme_retest",
        {
            "side": "BUY",
            "link_stoch_strength": "strong_up",
            "link_stoch_retest_zone": "oversold",
            "link_stoch_price_pullback_confirmed": True,
            "link_stoch_retest_confirmed": True,
            "link_stoch_retest_data_provenance": "observed historical oscillator and price behavior",
        },
    )
    blocked = evaluate_module(
        "link_stochastic_extreme_retest",
        {
            "side": "BUY",
            "link_stoch_strength": "strong_up",
            "link_stoch_retest_zone": "oversold",
            "link_stoch_price_pullback_confirmed": False,
            "link_stoch_retest_confirmed": True,
            "link_stoch_retest_data_provenance": "observed historical oscillator and price behavior",
        },
    )
    assert buy["view"] == "BUY"
    assert buy["link_stoch_retest_action"] == "BUY_CONFIRMED_EXTREME_RETEST"
    assert blocked["view"] == "WAIT"
    assert blocked["link_stoch_retest_action"] == "PULLBACK_NOT_CONFIRMED"


def test_link_rsi_extreme_exit_is_a_causal_exit_from_oversold_or_overbought():
    buy = evaluate_module(
        "link_rsi_extreme_exit",
        {
            "side": "BUY",
            "link_rsi_current": 34.0,
            "link_rsi_previous": 28.0,
            "link_rsi_oversold": 30.0,
            "link_rsi_overbought": 70.0,
            "link_rsi_extreme_data_provenance": "observed historical oscillator values",
        },
    )
    sell = evaluate_module(
        "link_rsi_extreme_exit",
        {
            "side": "SELL",
            "link_rsi_current": 66.0,
            "link_rsi_previous": 72.0,
            "link_rsi_oversold": 30.0,
            "link_rsi_overbought": 70.0,
            "link_rsi_extreme_data_provenance": "observed historical oscillator values",
        },
    )
    no_exit = evaluate_module(
        "link_rsi_extreme_exit",
        {
            "side": "BUY",
            "link_rsi_current": 45.0,
            "link_rsi_previous": 40.0,
            "link_rsi_oversold": 30.0,
            "link_rsi_overbought": 70.0,
            "link_rsi_extreme_data_provenance": "observed historical oscillator values",
        },
    )

    assert buy["view"] == "BUY"
    assert buy["link_rsi_extreme_action"] == "BUY_OUT_OF_OVERSOLD"
    assert sell["view"] == "SELL"
    assert sell["link_rsi_extreme_action"] == "SELL_OUT_OF_OVERBOUGHT"
    assert no_exit["link_rsi_extreme_action"] == "NO_RSI_EXTREME_EXIT"


def test_link_rsi_pattern_break_requires_explicit_observed_pattern_confirmation():
    confirmed = evaluate_module(
        "link_rsi_pattern_break",
        {
            "side": "BUY",
            "link_rsi_pattern_direction": "up",
            "link_rsi_pattern_confirmed": True,
            "link_rsi_pattern_name": "trendline_break",
            "link_rsi_pattern_data_provenance": "observed historical oscillator pattern",
        },
    )
    unconfirmed = evaluate_module(
        "link_rsi_pattern_break",
        {
            "side": "BUY",
            "link_rsi_pattern_direction": "up",
            "link_rsi_pattern_confirmed": False,
            "link_rsi_pattern_name": "trendline_break",
            "link_rsi_pattern_data_provenance": "observed historical oscillator pattern",
        },
    )

    assert confirmed["view"] == "BUY"
    assert confirmed["link_rsi_pattern_action"] == "BUY_CONFIRMED_PATTERN_BREAK"
    assert unconfirmed["view"] == "WAIT"
    assert unconfirmed["link_rsi_pattern_action"] == "PATTERN_NOT_CONFIRMED"


def test_link_rsi_fifty_line_entry_uses_a_fresh_cross_above_fifty():
    result = evaluate_module("link_rsi_fifty_line_entry", _rsi_state())

    assert result["applicability"] == "APPLICABLE"
    assert result["view"] == "BUY"
    assert result["link_rsi_action"] == "BUY_RSI_50_CROSS"
    assert result["link_rsi_fifty_cross"] == "UP"
    assert result["execution_authority"] is False


def test_link_rsi_fifty_line_entry_supports_a_stall_and_mirrors_downward():
    stall = evaluate_module(
        "link_rsi_fifty_line_entry",
        _rsi_state(link_rsi_current=50.5, link_rsi_previous=54.0, link_rsi_stall_confirmed=True),
    )
    sell = evaluate_module(
        "link_rsi_fifty_line_entry",
        _rsi_state(side="SELL", link_rsi_current=48.0, link_rsi_previous=51.0),
    )

    assert stall["link_rsi_action"] == "BUY_RSI_50_STALL"
    assert stall["link_rsi_fifty_cross"] == "NONE"
    assert sell["view"] == "SELL"
    assert sell["link_rsi_action"] == "SELL_RSI_50_CROSS"
    assert sell["link_rsi_fifty_cross"] == "DOWN"


def test_link_rsi_fifty_line_entry_keeps_confirmed_above_or_below_fifty_trend():
    buy = evaluate_module(
        "link_rsi_fifty_line_entry",
        _rsi_state(link_rsi_current=58.0, link_rsi_previous=55.0),
    )
    sell = evaluate_module(
        "link_rsi_fifty_line_entry",
        _rsi_state(side="SELL", link_rsi_current=42.0, link_rsi_previous=45.0),
    )

    assert buy["view"] == "BUY"
    assert buy["link_rsi_action"] == "BUY_RSI_ABOVE_50"
    assert sell["view"] == "SELL"
    assert sell["link_rsi_action"] == "SELL_RSI_BELOW_50"


def test_link_rsi_fifty_line_entry_fails_closed_for_unconfirmed_stall_or_bad_range():
    no_signal = evaluate_module(
        "link_rsi_fifty_line_entry",
        _rsi_state(link_rsi_current=51.0, link_rsi_previous=52.0),
    )
    bad = evaluate_module(
        "link_rsi_fifty_line_entry",
        _rsi_state(link_rsi_current=101.0),
    )

    assert no_signal["link_rsi_action"] == "NO_RSI_50_SIGNAL"
    assert bad["link_rsi_action"] == "INVALID_RSI_INPUT"


def test_link_macd_signal_line_entry_follows_the_line_relationship():
    buy = evaluate_module("link_macd_signal_line_entry", _macd_state())
    sell = evaluate_module(
        "link_macd_signal_line_entry",
        _macd_state(side="SELL", link_macd_line=-0.002, link_macd_signal_line=0.001),
    )

    assert buy["view"] == "BUY"
    assert buy["link_macd_action"] == "BUY_MACD_ABOVE_SIGNAL"
    assert sell["view"] == "SELL"
    assert sell["link_macd_action"] == "SELL_MACD_BELOW_SIGNAL"
    assert buy["execution_authority"] is False


def test_link_macd_signal_line_entry_waits_on_equality_and_rejects_unobserved_data():
    equal = evaluate_module(
        "link_macd_signal_line_entry",
        _macd_state(link_macd_line=0.002, link_macd_signal_line=0.002),
    )
    missing = evaluate_module(
        "link_macd_signal_line_entry",
        _macd_state(link_macd_data_provenance="synthetic fixture"),
    )

    assert equal["link_macd_action"] == "NO_MACD_RELATIONSHIP"
    assert missing["applicability"] == "MISSING_DATA"
