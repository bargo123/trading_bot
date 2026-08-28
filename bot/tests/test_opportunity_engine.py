from __future__ import annotations

import pytest

from aegis.intel.opportunity_engine import (
    FrozenOpportunity,
    freeze_opportunity,
    ordered_execution_attempts,
    rank_and_allocate,
)


def _candidate(name, *, symbol, thesis, p_capture, ev, lcb=0.0, risk=0.10,
               side="buy", lane="exploration", mechanism="micro", horizon=5):
    return {
        "candidate_id": name,
        "symbol": symbol,
        "side": side,
        "lane": lane,
        "mechanism": mechanism,
        "horizon_s": horizon,
        "thesis_key": thesis,
        "p_captured_win": p_capture,
        "expected_net_ev": ev,
        "expected_net_ev_lcb95": lcb,
        "tail_loss_probability": 0.02,
        "expected_time_to_green_s": 3.0,
        "fast_winner_similarity": 0.2,
        "fast_loser_similarity": 0.0,
        "marginal_risk_usd": risk,
        "portfolio_ok": True,
    }


def test_global_ranking_prefers_later_symbol_with_higher_capture_probability():
    ranked, selected = rank_and_allocate(
        [
            _candidate("early", symbol="EURUSD", thesis="t1", p_capture=0.62, ev=0.08),
            _candidate("later", symbol="GBPUSD", thesis="t2", p_capture=0.81, ev=0.05),
        ],
        max_positions=1,
    )
    assert [row["candidate_id"] for row in ranked] == ["later", "early"]
    assert [row["candidate_id"] for row in selected] == ["later"]


def test_global_ranking_uses_capture_probability_before_winner_similarity_and_ev():
    high_confidence = _candidate(
        "high-confidence", symbol="EURUSD", thesis="t1",
        p_capture=0.97, ev=0.05, lcb=0.80,
    )
    high_winner_similarity = _candidate(
        "high-winner-similarity", symbol="GBPUSD", thesis="t2",
        p_capture=0.90, ev=100.0, lcb=0.80,
    )
    high_winner_similarity["fast_winner_similarity"] = 1.0

    ranked, _ = rank_and_allocate(
        [high_winner_similarity, high_confidence], max_positions=1
    )

    assert ranked[0]["candidate_id"] == "high-confidence"


def test_global_allocator_blocks_duplicate_theses_but_allows_independent_entries():
    ranked, selected = rank_and_allocate(
        [
            _candidate("best", symbol="EURUSD", thesis="same", p_capture=0.80, ev=0.10),
            _candidate("duplicate", symbol="EURUSD", thesis="same", p_capture=0.79, ev=0.12),
            _candidate("independent", symbol="GBPUSD", thesis="other", p_capture=0.70, ev=0.04),
        ],
        max_positions=2,
    )
    assert len(ranked) == 3
    assert [row["candidate_id"] for row in selected] == ["best", "independent"]


def test_global_allocator_never_selects_nonpositive_or_portfolio_rejected_candidate():
    _, selected = rank_and_allocate(
        [
            _candidate("negative", symbol="EURUSD", thesis="n", p_capture=0.99, ev=-0.01),
            {**_candidate("blocked", symbol="GBPUSD", thesis="b", p_capture=0.99, ev=0.20),
             "portfolio_ok": False},
        ],
        max_positions=2,
    )
    assert selected == []


def test_ranked_candidate_is_frozen_and_keeps_execution_identity():
    candidate = _candidate("frozen", symbol="EURUSD", thesis="t1", p_capture=0.8, ev=0.1)
    frozen = freeze_opportunity(candidate)

    assert isinstance(frozen, FrozenOpportunity)
    assert frozen["candidate_id"] == "frozen"
    assert frozen["side"] == "buy"
    assert frozen.to_dict()["expected_net_ev"] == 0.1
    with pytest.raises(TypeError):
        frozen["side"] = "sell"


def test_frozen_candidate_also_freezes_nested_decision_journal():
    frozen = freeze_opportunity({"decision_journal": {"side": "buy", "reasons": ["ev"]}})

    with pytest.raises(TypeError):
        frozen["decision_journal"]["side"] = "sell"
    assert frozen["decision_journal"]["reasons"] == ("ev",)


def test_allocator_returns_the_exact_frozen_object_it_ranked():
    candidate = _candidate("same-object", symbol="EURUSD", thesis="t1", p_capture=0.8, ev=0.1)
    ranked, selected = rank_and_allocate([candidate], max_positions=1)

    assert isinstance(ranked[0], FrozenOpportunity)
    assert selected[0] is ranked[0]
    assert selected[0]["candidate_id"] == "same-object"


def test_complete_variant_pool_reaches_one_global_ranking():
    candidates = [
        _candidate("eur-buy", symbol="EURUSD", thesis="eur-buy", p_capture=0.61,
                   ev=0.01, side="buy", mechanism="momentum", horizon=3),
        _candidate("eur-sell", symbol="EURUSD", thesis="eur-sell", p_capture=0.55,
                   ev=0.02, side="sell", mechanism="reversal", horizon=8),
        _candidate("gbp-buy", symbol="GBPUSD", thesis="gbp-buy", p_capture=0.48,
                   ev=0.03, side="buy", mechanism="breakout", horizon=5),
        _candidate("gbp-sell", symbol="GBPUSD", thesis="gbp-sell", p_capture=0.68,
                   ev=0.01, side="sell", mechanism="snapback", horizon=10),
    ]

    ranked, selected = rank_and_allocate(candidates, max_positions=1)

    assert {row["candidate_id"] for row in ranked} == {
        "eur-buy", "eur-sell", "gbp-buy", "gbp-sell",
    }
    assert selected[0]["candidate_id"] == "gbp-sell"
    assert selected[0]["side"] == "sell"


def test_validated_lane_is_rankable_and_exploration_is_fallback():
    validated = _candidate(
        "validated", symbol="EURUSD", thesis="validated", p_capture=0.80,
        ev=0.10, lane="validated",
    )
    exploration = _candidate(
        "exploration", symbol="GBPUSD", thesis="exploration", p_capture=0.70,
        ev=0.20, lane="exploration",
    )

    ranked, selected = rank_and_allocate([exploration, validated], max_positions=1)

    assert ranked[0]["candidate_id"] == "validated"
    assert selected[0]["lane"] == "validated"

    _, fallback = rank_and_allocate([exploration], max_positions=1)
    assert fallback[0]["candidate_id"] == "exploration"


def test_forced_demo_lane_is_rankable_without_probability_or_positive_ev():
    forced = _candidate(
        "forced", symbol="EURUSD", thesis="forced", p_capture=0.70, ev=0.10,
        lane="FORCED_DEMO_EXPLORATION",
    )
    forced.update({
        "p_captured_win": None,
        "expected_net_ev": None,
        "expected_net_ev_lcb95": None,
        "authority_type": "FORCED_DEMO_EXPLORATION",
        "calibration_status": "UNCALIBRATED",
        "selection_score": 0.42,
    })

    ranked, selected = rank_and_allocate([forced], max_positions=1)

    assert len(ranked) == 1
    assert selected[0]["candidate_id"] == "forced"
    assert selected[0]["p_captured_win"] is None


def test_forced_demo_score_penalizes_repeated_broker_negative_net_states():
    from types import SimpleNamespace
    from aegis.intel.firehose_brain import _forced_demo_score

    candidate = SimpleNamespace(stop_pips=1.0)
    baseline = _forced_demo_score(
        candidate, {"net_target_pips": 1.0}, {}, [],
    )
    penalized = _forced_demo_score(
        candidate,
        {"net_target_pips": 1.0},
        {"broker_negative_net_penalty": 0.70},
        [],
    )

    assert penalized < baseline


def test_nineteen_ranked_candidates_fall_through_after_selected_failure():
    candidates = [
        _candidate(
            f"candidate-{index}",
            symbol=f"FX{index:02d}",
            thesis=f"thesis-{index}",
            p_capture=0.99 - index * 0.01,
            ev=0.10,
        )
        for index in range(19)
    ]

    ranked, selected = rank_and_allocate(candidates, max_positions=1)
    attempted = []
    for row in ordered_execution_attempts(ranked, selected):
        attempted.append(row["candidate_id"])
        if row["candidate_id"] == "candidate-2":
            break

    assert len(ranked) == 19
    assert [row["candidate_id"] for row in selected] == ["candidate-0"]
    assert attempted == ["candidate-0", "candidate-1", "candidate-2"]
