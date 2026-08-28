from __future__ import annotations

from aegis.research.book_strategy_evidence import (
    compact_context_event,
    evaluate_compiled_strategy,
    evaluate_strategy_evidence,
)


def test_context_snapshot_is_point_in_time_and_hashed():
    snapshot = compact_context_event({
        "timestamp": 10,
        "symbol": "EURUSD",
        "bid": 1.1,
        "ask": 1.1001,
        "future_quote": 9,
    })
    assert snapshot["symbol"] == "EURUSD"
    assert "future_quote" not in snapshot
    assert len(snapshot["context_hash"]) == 64


def test_buy_rule_requires_explicit_inputs():
    strategy = {
        "status": "CODED_EXACT",
        "side_rule": "BUY",
        "compiled_rule": {"return_1s_gte": 0.0001},
    }
    result = evaluate_compiled_strategy(strategy, {"side": "BUY"})
    assert result["status"] == "MISSING_INPUT"
    assert "return_1s" in result["missing"]


def test_explicit_rule_matches_only_when_all_predicates_hold():
    strategy = {
        "status": "CODED_EXACT",
        "side_rule": "BUY",
        "compiled_rule": {"return_1s_gte": 0.0001, "spread_max": 1.5},
    }
    result = evaluate_compiled_strategy(
        strategy,
        {"side": "BUY", "return_1s": 0.0002, "spread": 1.2},
    )
    assert result["status"] == "MATCH"
    assert result["failed_predicates"] == []


def test_proxy_strategy_cannot_emit_exact_match():
    result = evaluate_strategy_evidence(
        {"status": "FAMILY_PROXY", "strategy_family": "momentum"},
        {"side": "BUY"},
    )
    assert result["evidence_status"] == "FAMILY_PROXY"
    assert result["evaluation_status"] == "CONTEXT_ONLY"
