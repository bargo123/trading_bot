from __future__ import annotations

from aegis.intel.opportunity_engine import rank_and_allocate


def _candidate(name, *, symbol, thesis, p_capture, ev, lcb=0.0, risk=0.10):
    return {
        "candidate_id": name,
        "symbol": symbol,
        "side": "buy",
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
