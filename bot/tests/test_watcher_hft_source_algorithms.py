from __future__ import annotations

import pytest

from aegis.research.watcher_algorithms import evaluate_module


DEVELOPING_SOURCE = "Developing High-Frequency Trading Systems"
CARTEA_SOURCE = "Modelling Asset Prices for Algorithmic and High-Frequency Trading"


def _flow(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "developing_hft_flow_direction": "up",
        "developing_hft_flow_size": "large",
        "developing_hft_flow_exhausted": False,
        "developing_hft_data_provenance": "causal_order_flow_observation",
    }
    state.update(overrides)
    return state


def _rebate(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "cartea_regime_persistence": 0.8,
        "cartea_zero_revision_probability": 0.99,
        "cartea_revision_volatility": 0.0003,
        "cartea_rebate_net_edge": 0.0001,
        "cartea_rebate_safety_status": "safe",
        "cartea_regime_data_provenance": "causal_hmm_regime_observation",
    }
    state.update(overrides)
    return state


def _inventory(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "SELL",
        "cartea_inventory_units": 2,
        "cartea_target_inventory_units": 0,
        "cartea_time_to_flatten_s": 30,
        "cartea_inventory_data_provenance": "causal_inventory_observation",
    }
    state.update(overrides)
    return state


def _liquidity(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "developing_hft_depth_levels": 5,
        "developing_hft_volume_per_layer": 100.0,
        "developing_hft_liquidity_state": "deep_broad",
        "developing_hft_liquidity_provenance": "observed_live_order_book_depth",
    }
    state.update(overrides)
    return state


def _volatility_cluster(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "developing_hft_abs_return_current": 0.0008,
        "developing_hft_abs_return_prior": 0.0007,
        "developing_hft_volatility_cluster_state": "high_cluster",
        "developing_hft_volatility_observation_n": 200,
        "developing_hft_volatility_provenance": "observed_raw_tick_returns",
    }
    state.update(overrides)
    return state


def _stat_arb(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "developing_hft_pair_id": "EURUSD:GBPUSD",
        "developing_hft_pair_dislocation": 2.4,
        "developing_hft_pair_direction": "BUY",
        "developing_hft_pair_relationship_status": "validated_stationary_relationship",
        "developing_hft_pair_observation_n": 500,
        "developing_hft_pair_net_edge_after_cost": 0.0002,
        "developing_hft_pair_quotes_synchronized": True,
        "developing_hft_pair_data_provenance": "observed_synchronized_multi_venue_quotes",
    }
    state.update(overrides)
    return state


def _news(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "developing_hft_news_direction": "BUY",
        "developing_hft_news_release_age_s": 0.4,
        "developing_hft_news_relevance": 0.9,
        "developing_hft_news_window_open": True,
        "developing_hft_news_expected_net_edge": 0.0003,
        "developing_hft_news_observation_n": 1,
        "developing_hft_news_provenance": "verified timestamped public news",
        "developing_hft_news_confirmation": "confirmed",
    }
    state.update(overrides)
    return state


def test_developing_hft_flow_uses_large_flow_and_drying_flow_as_distinct_states():
    buy = evaluate_module("developing_hft_flow_exhaustion", _flow())
    sell = evaluate_module(
        "developing_hft_flow_exhaustion",
        _flow(side="SELL", developing_hft_flow_direction="down"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["source_books"] == [DEVELOPING_SOURCE]

    exhausted = evaluate_module("developing_hft_flow_exhaustion", _flow(developing_hft_flow_exhausted=True))
    assert exhausted["view"] == "WAIT"
    assert exhausted["developing_hft_reversal_risk"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"developing_hft_flow_size": "medium"},
        {"developing_hft_flow_direction": "sideways"},
    ],
)
def test_developing_hft_flow_waits_without_a_directional_large_flow(overrides):
    result = evaluate_module("developing_hft_flow_exhaustion", _flow(**overrides))
    assert result["view"] == "WAIT"
    assert result["reasons"]


def test_developing_hft_liquidity_requires_real_depth_and_distinguishes_thin_books():
    liquid = evaluate_module("developing_hft_liquidity_depth", _liquidity())
    thin = evaluate_module(
        "developing_hft_liquidity_depth",
        _liquidity(developing_hft_liquidity_state="thin"),
    )
    assert liquid["view"] == "WAIT"
    assert liquid["developing_hft_liquidity_assessment"] == "DEEP_BROAD"
    assert liquid["directional_claim"] is False
    assert thin["developing_hft_liquidity_assessment"] == "THIN"

    proxy = evaluate_module(
        "developing_hft_liquidity_depth",
        _liquidity(developing_hft_liquidity_provenance="tick_volume_proxy"),
    )
    assert proxy["applicability"] == "MISSING_DATA"


def test_developing_hft_volatility_clustering_records_tail_regime_without_direction():
    clustered = evaluate_module("developing_hft_volatility_clustering", _volatility_cluster())
    quiet = evaluate_module(
        "developing_hft_volatility_clustering",
        _volatility_cluster(
            developing_hft_abs_return_current=0.0002,
            developing_hft_abs_return_prior=0.0007,
            developing_hft_volatility_cluster_state="quiet",
        ),
    )
    assert clustered["view"] == "WAIT"
    assert clustered["developing_hft_volatility_assessment"] == "HIGH_CLUSTER"
    assert clustered["developing_hft_tail_risk_warning"] is True
    assert quiet["developing_hft_volatility_assessment"] == "QUIET"
    assert quiet["developing_hft_tail_risk_warning"] is False


def test_developing_hft_stat_arb_requires_validated_pair_data_and_after_cost_edge():
    buy = evaluate_module("developing_hft_stat_arb_dislocation", _stat_arb())
    sell = evaluate_module(
        "developing_hft_stat_arb_dislocation",
        _stat_arb(side="SELL", developing_hft_pair_direction="SELL"),
    )
    assert buy["view"] == "BUY"
    assert sell["view"] == "SELL"
    assert buy["developing_hft_pair_id"] == "EURUSD:GBPUSD"

    negative = evaluate_module(
        "developing_hft_stat_arb_dislocation",
        _stat_arb(developing_hft_pair_net_edge_after_cost=0.0),
    )
    assert negative["view"] == "WAIT"
    assert negative["developing_hft_stat_arb_assessment"] == "NEGATIVE_NET_EDGE"


def test_developing_hft_news_impact_needs_verified_event_and_open_window():
    result = evaluate_module("developing_hft_news_impact", _news())
    assert result["view"] == "BUY"
    assert result["developing_hft_news_assessment"] == "ACTIONABLE_EVENT"

    closed = evaluate_module(
        "developing_hft_news_impact",
        _news(developing_hft_news_window_open=False),
    )
    assert closed["view"] == "WAIT"
    assert closed["developing_hft_news_assessment"] == "WINDOW_CLOSED"

    unverified = evaluate_module(
        "developing_hft_news_impact",
        _news(developing_hft_news_provenance="unverified social rumor"),
    )
    assert unverified["applicability"] == "MISSING_DATA"


def test_cartea_rebate_safety_requires_regime_evidence_and_positive_net_edge():
    result = evaluate_module("cartea_regime_rebate_safety", _rebate())
    assert result["view"] == "WAIT"
    assert result["cartea_rebate_eligible"] is True
    assert result["directional_claim"] is False
    assert result["source_books"] == [CARTEA_SOURCE]

    unsafe = evaluate_module("cartea_regime_rebate_safety", _rebate(cartea_rebate_safety_status="unknown"))
    assert unsafe["view"] == "MISSING_DATA"
    assert unsafe["applicability"] == "MISSING_DATA"

    negative = evaluate_module("cartea_regime_rebate_safety", _rebate(cartea_rebate_net_edge=-0.0001))
    assert negative["cartea_rebate_eligible"] is False


def test_cartea_inventory_skew_rebalances_toward_zero():
    sell = evaluate_module("cartea_inventory_skew", _inventory())
    buy = evaluate_module(
        "cartea_inventory_skew",
        _inventory(side="BUY", cartea_inventory_units=-2),
    )
    flat = evaluate_module("cartea_inventory_skew", _inventory(cartea_inventory_units=0, side="BUY"))
    assert sell["view"] == "SELL"
    assert buy["view"] == "BUY"
    assert flat["view"] == "WAIT"
    assert sell["cartea_inventory_target"] == 0.0


@pytest.mark.parametrize("algorithm_id", [
    "developing_hft_flow_exhaustion",
    "developing_hft_liquidity_depth",
    "developing_hft_volatility_clustering",
    "developing_hft_stat_arb_dislocation",
    "developing_hft_news_impact",
    "cartea_regime_rebate_safety",
    "cartea_inventory_skew",
])
def test_hft_source_algorithms_fail_closed_without_provenance(algorithm_id):
    result = evaluate_module(algorithm_id, {"symbol": "EURUSD", "side": "BUY"})
    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
    assert result["execution_authority"] is False


def _quote_matching(**overrides):
    state = {
        "symbol": "EURUSD",
        "side": "BUY",
        "aldridge_quote_match_identity_available": True,
        "aldridge_quote_match_direction": "up",
        "aldridge_quote_match_persistence_confirmed": "confirmed",
        "aldridge_quote_match_probability": 0.70,
        "aldridge_quote_match_expected_move": 0.0010,
        "aldridge_quote_match_total_cost": 0.0001,
        "aldridge_quote_match_data_provenance": "observed identified order-flow history",
    }
    state.update(overrides)
    return state


def test_aldridge_quote_matching_requires_identity_persistence_and_after_cost_edge():
    result = evaluate_module("aldridge_quote_matching", _quote_matching())
    anonymous = evaluate_module(
        "aldridge_quote_matching",
        _quote_matching(aldridge_quote_match_identity_available=False),
    )

    assert result["view"] == "BUY"
    assert result["aldridge_quote_match_action"] == "IDENTIFIED_PERSISTENT_IMPACT"
    assert result["aldridge_quote_match_net_edge"] == pytest.approx(0.0003)
    assert result["aldridge_quote_match_identity_available"] is True
    assert anonymous["view"] == "WAIT"
    assert anonymous["aldridge_quote_match_action"] == "ANONYMOUS_MARKET_INFEASIBLE"
    assert anonymous["execution_authority"] is False


def test_aldridge_quote_matching_rejects_unpersistent_or_negative_impact():
    unconfirmed = evaluate_module(
        "aldridge_quote_matching",
        _quote_matching(aldridge_quote_match_persistence_confirmed="unconfirmed"),
    )
    negative = evaluate_module(
        "aldridge_quote_matching",
        _quote_matching(aldridge_quote_match_probability=0.51, aldridge_quote_match_total_cost=0.001),
    )

    assert unconfirmed["aldridge_quote_match_action"] == "PERSISTENCE_NOT_CONFIRMED"
    assert negative["aldridge_quote_match_action"] == "NO_POSITIVE_AFTER_COST_EDGE"
    assert negative["view"] == "WAIT"


def test_aldridge_quote_matching_rejects_synthetic_order_identity():
    result = evaluate_module(
        "aldridge_quote_matching",
        _quote_matching(aldridge_quote_match_data_provenance="synthetic fixture"),
    )

    assert result["view"] == "MISSING_DATA"
    assert result["applicability"] == "MISSING_DATA"
