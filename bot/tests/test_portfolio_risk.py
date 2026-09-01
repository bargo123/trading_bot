from __future__ import annotations

import math

import pytest

from aegis.engines import PositionSnapshot
from aegis.portfolio_risk import (
    fx_legs,
    portfolio_allows,
    portfolio_exposure,
    portfolio_pretrade_decision,
)


def position(
    symbol: str = "EURUSD",
    side: str = "buy",
    quantity: float = 0.1,
    avg_price: float = 1.1,
) -> PositionSnapshot:
    return PositionSnapshot(symbol, side, quantity, avg_price)  # type: ignore[arg-type]


def test_fx_legs_parse_base_and_quote_direction_for_buys_and_sells():
    assert fx_legs("eurusd", "buy", 0.1) == {"EUR": 1, "USD": -1}
    assert fx_legs("EURUSD", "sell", 0.1) == {"EUR": -1, "USD": 1}


def test_configured_audsgd_pair_has_real_base_and_quote_legs():
    assert fx_legs("AUDSGD", "buy", 0.1) == {"AUD": 1, "SGD": -1}
    assert portfolio_allows([], position("AUDSGD", avg_price=0.9), {}) == (True, "")


def test_buy_eurusd_and_buy_gbpusd_share_short_usd_factor():
    positions = [position("EURUSD", "buy", 0.1, 1.1)]
    candidate = position("GBPUSD", "buy", 0.1, 1.3)
    ok, reason = portfolio_allows(
        positions,
        candidate,
        {
            "max_positions": 8,
            "max_per_symbol": 1,
            "max_currency_direction_positions": 1,
        },
    )
    assert not ok
    assert reason == "currency_factor:USD:short"


def test_opposite_currency_leg_offsets_directional_count():
    positions = [position("EURUSD", "buy", 0.1, 1.1)]
    candidate = position("USDJPY", "buy", 0.1, 150.0)
    assert portfolio_allows(
        positions,
        candidate,
        {
            "max_positions": 8,
            "max_per_symbol": 1,
            "max_currency_direction_positions": 1,
        },
    ) == (True, "")


def test_exposure_counts_every_existing_position_and_the_candidate():
    positions = [
        position("EURUSD", "buy"),
        position("GBPUSD", "buy", avg_price=1.3),
    ]
    candidate = position("AUDUSD", "buy", avg_price=0.7)
    assert portfolio_exposure(positions) == {"EUR": 1, "USD": -2, "GBP": 1}
    assert portfolio_allows(
        positions,
        candidate,
        {
            "max_positions": 8,
            "max_per_symbol": 1,
            "max_currency_direction_positions": 2,
        },
    ) == (False, "currency_factor:USD:short")


def test_portfolio_and_symbol_caps_include_the_proposed_position():
    held = [position("EURUSD")]
    assert portfolio_allows(
        held,
        position("GBPUSD", avg_price=1.3),
        {"max_positions": 1, "max_per_symbol": 2},
    ) == (False, "max_positions")
    assert portfolio_allows(
        held,
        position("EURUSD"),
        {"max_positions": 8, "max_per_symbol": 1},
    ) == (False, "max_per_symbol")


def test_known_non_fx_shape_has_no_currency_legs_but_still_gets_symbol_gate():
    assert fx_legs("MGC", "buy", 1.0) == {}
    assert portfolio_allows(
        [position("MGC", quantity=1.0, avg_price=3500.0)],
        position("mgc", quantity=1.0, avg_price=3501.0),
        {"max_positions": 8, "max_per_symbol": 1},
    ) == (False, "max_per_symbol")


@pytest.mark.parametrize("side", ["", "hold", "BUY ", None])
def test_unknown_or_malformed_side_fails_closed(side):
    candidate = position(side=side)  # type: ignore[arg-type]
    assert fx_legs(candidate.symbol, candidate.side, candidate.quantity) == {}
    assert portfolio_allows([], candidate, {}) == (False, "invalid_candidate:side")


@pytest.mark.parametrize(
    "symbol",
    [
        "EUR/USD",
        "EURUSDm",
        "MGCUSD",
        "ZZZUSD",
        "EURUS",
        "ABC12",
        "",
        " EURUSD",
        None,
    ],
)
def test_unknown_or_malformed_symbol_fails_closed(symbol):
    candidate = position(symbol=symbol)  # type: ignore[arg-type]
    assert fx_legs(candidate.symbol, candidate.side, candidate.quantity) == {}
    assert portfolio_allows([], candidate, {}) == (False, "invalid_candidate:symbol")


@pytest.mark.parametrize("quantity", [0.0, -0.1, math.nan, math.inf, -math.inf, "bad"])
def test_nonpositive_nonfinite_or_malformed_candidate_quantity_fails_closed(quantity):
    candidate = position(quantity=quantity)  # type: ignore[arg-type]
    assert fx_legs(candidate.symbol, candidate.side, candidate.quantity) == {}
    assert portfolio_allows([], candidate, {}) == (False, "invalid_candidate:quantity")


def test_malformed_existing_position_cannot_be_silently_omitted_from_exposure():
    malformed = position("EURUSD", quantity=math.nan)
    with pytest.raises(ValueError, match="invalid_position:0:quantity"):
        portfolio_exposure([malformed])
    assert portfolio_allows([malformed], position("GBPUSD"), {}) == (
        False,
        "invalid_position:0:quantity",
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("max_positions", None),
        ("max_positions", math.nan),
        ("max_positions", -1),
        ("max_per_symbol", None),
        ("max_per_symbol", 1.5),
        ("max_per_symbol", False),
        ("max_currency_direction_positions", None),
        ("max_currency_direction_positions", math.inf),
        ("max_currency_direction_positions", "bad"),
    ],
)
def test_malformed_caps_fail_closed_with_the_exact_config_name(name, value):
    assert portfolio_allows([], position(), {name: value}) == (
        False,
        f"invalid_config:{name}",
    )


def test_pretrade_rejection_has_exact_cap_and_combined_exposure_map():
    ok, reason, event = portfolio_pretrade_decision(
        positions=[position("EURUSD", "buy")],
        symbol="GBPUSD",
        side="buy",
        quantity=0.1,
        avg_price=1.3,
        cfg={
            "max_positions": 8,
            "firehose_max_per_symbol": 1,
            "max_currency_direction_positions": 1,
        },
    )
    assert not ok
    assert reason == "currency_factor:USD:short"
    assert event == {
        "event": "portfolio_reject",
        "symbol": "GBPUSD",
        "side": "buy",
        "qty": 0.1,
        "reason": "currency_factor:USD:short",
        "cap": {"name": "max_currency_direction_positions", "value": 1},
        "exposure": {"EUR": 1, "GBP": 1, "USD": -2},
    }


def test_pretrade_uses_firehose_symbol_cap_and_journals_numeric_cap():
    ok, reason, event = portfolio_pretrade_decision(
        positions=[position("EURUSD")],
        symbol="eurusd",
        side="buy",
        quantity=0.1,
        avg_price=1.2,
        cfg={"max_positions": 8, "firehose_max_per_symbol": "1"},
    )
    assert not ok
    assert reason == "max_per_symbol"
    assert event is not None
    assert event["cap"] == {"name": "max_per_symbol", "value": 1}
