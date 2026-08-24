#!/usr/bin/env python3
"""Per-trade expected-value gate. Anchored on the real 91.91% WR / 0.71 PF failure."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aegis.intel.trade_economics import (
    evaluate_trade_economics,
    usd_per_price_unit,
    wilson_lower_bound,
)

# Real MetaQuotes-Demo EURUSD spec, read from mt5.symbol_info.
# 1.0 / 1e-05 = 100_000 USD per 1.0 of price per lot -> $1000 at 0.01 lots.
EURUSD_SPEC = {
    "trade_tick_size": 0.00001,
    "trade_tick_value": 1.0,
    "trade_tick_value_loss": 1.0,
    "trade_contract_size": 100000.0,
    "point": 0.00001,
}
# Real USDJPY spec. contract_size alone would be wrong by ~158x here because the
# quote currency is not the account currency, which is why the tick pair wins.
USDJPY_SPEC = {
    "trade_tick_size": 0.001,
    "trade_tick_value": 0.6315563442992567,
    "trade_tick_value_loss": 0.6315603329586076,
    "trade_contract_size": 100000.0,
    "point": 0.001,
}
PIP = 0.0001


def _econ(**overrides):
    kwargs = {
        "side": "buy",
        "entry": 1.10000,
        "invalidation": 1.10000 - 10 * PIP,
        "target": 1.10000 + 20 * PIP,
        "lots": 0.01,
        "spec": EURUSD_SPEC,
        "spread_price": 0.5 * PIP,
        "commission_round_trip_usd": 0.0,
        "analogue_n": 100,
        "analogue_n_losses": 40,
    }
    kwargs.update(overrides)
    return evaluate_trade_economics(**kwargs)


def test_usd_per_price_unit_uses_broker_tick_pair():
    # 1.0 / 1e-05 = 100_000 per lot; 0.01 lots -> $1000 per 1.0 of price.
    assert usd_per_price_unit(EURUSD_SPEC, lots=0.01) == pytest.approx(1000.0)
    assert usd_per_price_unit(EURUSD_SPEC, lots=1.0) == pytest.approx(100000.0)


def test_usd_per_price_unit_prefers_tick_pair_over_contract_size_on_crosses():
    """USDJPY is quoted in JPY, so contract_size alone overstates USD risk ~158x."""
    tick_based = usd_per_price_unit(USDJPY_SPEC, lots=0.01)
    assert tick_based == pytest.approx(0.6315603329586076 / 0.001 * 0.01)
    assert tick_based == pytest.approx(6.3156, rel=1e-3)
    # The naive contract_size answer would be 1000.0 - two orders of magnitude out.
    assert usd_per_price_unit({"trade_contract_size": 100000.0}, lots=0.01) == pytest.approx(1000.0)


def test_usd_per_price_unit_falls_back_to_contract_size():
    spec = {"trade_contract_size": 100000.0}
    assert usd_per_price_unit(spec, lots=0.01) == pytest.approx(1000.0)


def test_missing_contract_value_is_rejected_not_treated_as_free():
    assert usd_per_price_unit({}, lots=0.01) is None
    result = _econ(spec={})
    assert not result.acceptable
    assert result.reason == "contract_value_unavailable"


def test_one_pip_target_over_thirty_pip_stop_is_rejected():
    """The exact regression: 1-pip TP / 30-pip SL must never reach FIRE."""
    result = _econ(
        invalidation=1.10000 - 30 * PIP,
        target=1.10000 + 1 * PIP,
        analogue_n=1000,
        analogue_n_losses=81,  # 91.9% historical win rate
    )
    assert not result.acceptable
    assert result.reason == "payoff_below_floor"
    # Structure is rejected before the win rate can argue for it.
    assert result.p_win is not None and result.p_win > 0.89
    assert result.payoff_ratio is not None and result.payoff_ratio < 0.05


def test_high_win_rate_cannot_rescue_negative_expected_value():
    """WR 91.91% with PF < 1 must be rejected on EV, per the reference failure."""
    # 3-pip reward, 4-pip risk clears the 1.0R floor only if we lower it; use an
    # explicit payoff floor of 0 so the EV test is what does the rejecting.
    result = _econ(
        invalidation=1.10000 - 4 * PIP,
        target=1.10000 + 3 * PIP,
        p_win=0.9191,
        min_payoff_ratio=0.0,
        spread_price=3.0 * PIP,
    )
    assert not result.acceptable
    assert result.reason == "expected_net_value_not_positive"
    assert result.expected_net_value_usd is not None
    assert result.expected_net_value_usd <= 0


def test_genuine_positive_expectancy_trade_is_accepted():
    result = _econ(p_win=0.55)
    assert result.acceptable
    assert result.reason == "positive_expected_net_value"
    # 0.01-lot EURUSD: $1000 per 1.0 of price, so 1 pip = $0.10.
    # 20 pips reward = $2.00, 10 pips risk = $1.00.
    assert result.expected_win_usd == pytest.approx(2.00)
    assert result.expected_loss_usd == pytest.approx(1.00)
    assert result.payoff_ratio == pytest.approx(2.0)
    # cost = 0.5 pip * $1000/price = $0.05
    assert result.cost_usd == pytest.approx(0.05)
    # EV = .55*2.00 - .45*1.00 - .05 = 1.10 - 0.45 - 0.05 = 0.60
    assert result.expected_net_value_usd == pytest.approx(0.60)
    # breakeven = (1.00 + 0.05) / (2.00 + 1.00) = 0.35
    assert result.breakeven_win_rate == pytest.approx(0.35)


def test_cost_is_charged_and_can_flip_a_marginal_trade():
    cheap = _econ(p_win=0.36, spread_price=0.0)
    dear = _econ(p_win=0.36, spread_price=8.0 * PIP)
    assert cheap.acceptable
    assert not dear.acceptable
    assert dear.reason == "expected_net_value_not_positive"
    assert dear.cost_usd is not None and dear.cost_usd > cheap.cost_usd


def test_commission_is_included_in_cost():
    free = _econ(p_win=0.55, commission_round_trip_usd=0.0)
    charged = _econ(p_win=0.55, commission_round_trip_usd=0.50)
    # Commission lands on cost and comes straight off expected value.
    assert charged.cost_usd == pytest.approx(free.cost_usd + 0.50)
    assert charged.expected_net_value_usd == pytest.approx(free.expected_net_value_usd - 0.50)
    # $0.50 does not flip a $0.60 edge, but a commission larger than the edge does.
    assert charged.acceptable
    swamped = _econ(p_win=0.55, commission_round_trip_usd=5.00)
    assert not swamped.acceptable
    assert swamped.reason == "expected_net_value_not_positive"


def test_measured_slippage_is_included_and_can_reject_net_ev():
    free = _econ(p_win=0.36, spread_price=0.0, slippage_price=0.0)
    slipped = _econ(p_win=0.36, spread_price=0.0, slippage_price=8.0 * PIP)

    assert free.acceptable
    assert not slipped.acceptable
    assert slipped.reason == "expected_net_value_not_positive"
    assert slipped.cost_usd is not None and free.cost_usd is not None
    assert slipped.cost_usd == pytest.approx(free.cost_usd + 0.80)


def test_invalidation_must_sit_on_the_losing_side():
    assert _econ(invalidation=1.10500).reason == "invalidation_not_below_entry"
    assert (
        _econ(side="sell", invalidation=1.09500, target=1.09000).reason
        == "invalidation_not_above_entry"
    )


def test_missing_invalidation_is_rejected():
    assert _econ(invalidation=None).reason == "no_structural_invalidation"


def test_absent_target_is_rejected_without_synthesised_geometry():
    result = _econ(target=None, p_win=0.6, min_payoff_ratio=1.5)
    assert not result.acceptable
    assert result.reason == "no_structural_target"
    assert result.target is None
    assert result.target_source == "none"


def test_target_behind_entry_is_rejected_not_replaced():
    result = _econ(target=1.09000, p_win=0.6)
    assert not result.acceptable
    assert result.reason == "target_not_above_entry"
    assert result.target == 1.09000
    assert result.target_source == "structure"


def test_sell_side_geometry_is_symmetric():
    result = _econ(
        side="sell",
        invalidation=1.10000 + 10 * PIP,
        target=1.10000 - 20 * PIP,
        p_win=0.55,
    )
    assert result.acceptable
    assert result.payoff_ratio == pytest.approx(2.0)
    assert result.expected_net_value_usd == pytest.approx(0.60)


def test_wilson_lower_bound_penalises_thin_samples():
    thin = wilson_lower_bound(wins=19, n=20)
    thick = wilson_lower_bound(wins=950, n=1000)
    assert thin is not None and thick is not None
    # Same 95% point estimate, but 20 observations support far less.
    assert thin < thick
    assert thin < 0.95
    assert wilson_lower_bound(wins=0, n=0) is None
    assert wilson_lower_bound(wins=0, n=10) == 0.0


def test_win_probability_defaults_to_conservative_analogue_bound():
    result = _econ(p_win=None, analogue_n=20, analogue_n_losses=1)
    assert result.p_win_source == "analogue_wilson_lower_bound"
    # 19/20 = 0.95 point estimate, but the bound must be materially lower.
    assert result.p_win is not None and result.p_win < 0.9


def test_no_evidence_and_no_supplied_probability_is_rejected():
    result = _econ(p_win=None, analogue_n=0, analogue_n_losses=0)
    assert not result.acceptable
    assert result.reason == "no_win_probability_evidence"


def test_zero_size_is_rejected():
    assert _econ(lots=0.0).reason == "no_position_size"


def test_journal_payload_explains_the_decision():
    payload = _econ(p_win=0.55).journal()
    for key in (
        "econ_ok",
        "econ_reason",
        "econ_expected_win_usd",
        "econ_expected_loss_usd",
        "econ_cost_usd",
        "econ_p_win",
        "econ_expected_net_usd",
        "econ_payoff_ratio",
        "econ_breakeven_wr",
    ):
        assert key in payload
    assert payload["econ_ok"] is True
